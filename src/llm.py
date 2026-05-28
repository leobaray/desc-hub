"""Cliente LLM pra COMPOR a descrição (Ollama Cloud por padrão; local se sem key).

Nunca usado pra extrair dado do invoice — extração é determinística. Pede saída
JSON (`format=json`). O modelo Aurora (qwen3.5) é de RACIOCÍNIO: sem `think=false`
ele gasta o orçamento de tokens "pensando" e devolve `content` vazio — por isso
desligamos o think, damos folga de tokens, extraímos o JSON de forma tolerante e
tentamos de novo em falha transitória. Se mesmo assim falhar, o compositor cai
pro modo determinístico.
"""
from __future__ import annotations

import json
import time

import httpx

from src.config import settings


class LLMIndisponivel(RuntimeError):
    """Falha na chamada — caller deve cair pro fallback determinístico."""


def _headers() -> dict:
    if settings.ollama_api_key:
        return {"Authorization": f"Bearer {settings.ollama_api_key}"}
    return {}


def disponivel() -> bool:
    # Cloud (api_key setado): confia — a chamada real tem retry + fallback.
    if settings.ollama_api_key:
        return True
    try:
        return httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


def _chamar(system: str, prompt: str) -> str:
    payload = {
        "model": settings.ollama_model,
        "format": "json",
        "stream": False,
        "think": False,
        "options": {"temperature": 0.2, "num_predict": 2500},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    r = httpx.post(
        f"{settings.ollama_base_url}/api/chat",
        json=payload,
        headers=_headers(),
        timeout=settings.llm_timeout,
    )
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(data["error"])
    return (data.get("message", {}) or {}).get("content", "") or ""


def _extrair_json(content: str) -> dict | None:
    content = content.strip()
    if not content:
        return None
    try:
        return json.loads(content)
    except Exception:
        pass
    # tolera texto em volta: pega do primeiro '{' ao último '}'
    i, j = content.find("{"), content.rfind("}")
    if 0 <= i < j:
        try:
            return json.loads(content[i : j + 1])
        except Exception:
            return None
    return None


def gerar_json(system: str, prompt: str) -> dict:
    # Paciente: 4 tentativas com backoff — o melhor é sair COM IA, não no fallback.
    erro = "sem resposta"
    backoff = [2, 4, 8]
    for tentativa in range(4):
        try:
            obj = _extrair_json(_chamar(system, prompt))
            if obj is not None:
                return obj
            erro = "conteúdo vazio ou sem JSON"
        except Exception as e:  # noqa: BLE001 — transitório vira retry; persistente vira fallback
            erro = str(e)
        if tentativa < len(backoff):
            time.sleep(backoff[tentativa])
    raise LLMIndisponivel(erro)
