"""Servidor web (FastAPI) do app de importação — LBWMA.

Rotas:
  GET  /               -> a página única
  POST /api/processar  -> recebe o PDF, devolve NDJSON streaming (item a item)
  POST /api/exportar   -> recebe as linhas (com edições) e devolve o xlsx

A extração é determinística; a composição pode usar o LLM (cloud) quando ia=true.
Tudo que não dá pra confirmar chega ao front marcado pra revisão.

Rodar:  python -m uvicorn src.web:app --reload   (ou: python run.py)
"""
from __future__ import annotations

import dataclasses
import json
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.descricao import compor, ler_cache_descricoes
from src.dominio import DescricaoDUIMP, ItemInvoice
from src.pipeline import processar_stream
from src.saida import exportar_xlsx
from src.specs import buscar_specs

FRONT_DIR = Path(__file__).parent / "frontend"

app = FastAPI(title="LBWMA — Importação")
app.mount("/static", StaticFiles(directory=FRONT_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (FRONT_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/api/processar")
async def api_processar(
    file: UploadFile = File(...),
    ia: bool = Query(False),
    limite: int | None = Query(None),
):
    dados = await file.read()
    tmp = Path(tempfile.gettempdir()) / f"invoice_{uuid.uuid4().hex}.pdf"
    tmp.write_bytes(dados)

    def gen():
        try:
            for tipo, payload in processar_stream(tmp, limite=limite, usar_llm=ia):
                if tipo == "item":
                    payload = dataclasses.asdict(payload)
                yield json.dumps({"tipo": tipo, "dado": payload}, ensure_ascii=False) + "\n"
        finally:
            tmp.unlink(missing_ok=True)

    return StreamingResponse(gen(), media_type="application/x-ndjson")


_CAMPOS = {f.name for f in dataclasses.fields(DescricaoDUIMP)}


@app.post("/api/exportar")
async def api_exportar(request: Request):
    body = await request.json()
    descricoes = [
        DescricaoDUIMP(**{k: v for k, v in linha.items() if k in _CAMPOS})
        for linha in body.get("linhas", [])
    ]
    destino = exportar_xlsx(descricoes, "descricoes_duimp.xlsx")
    return FileResponse(
        destino,
        filename="descricoes_duimp.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# --- Base de descrições (cache) — biblioteca pra montar a planilha-base --------
def _linhas_da_base() -> list[DescricaoDUIMP]:
    """A base = tudo que já foi redigido (cache de descrições), como linhas DUIMP.
    Sem qtd/origem: não é um embarque, é a biblioteca de descrições."""
    base = ler_cache_descricoes()
    linhas: list[DescricaoDUIMP] = []
    for cod in sorted(base, key=lambda c: (base[c].get("ncm_sugerida", ""), c)):
        c = base[cod]
        linhas.append(
            DescricaoDUIMP(
                codigo=cod,
                descricao=c.get("descricao", ""),
                ncm_sugerida=c.get("ncm_sugerida", ""),
                template=c.get("template", ""),
                fonte_url=c.get("fonte_url", ""),
                qtd_shipped="",
                origem="",
                precisa_revisao=c.get("precisa_revisao", False),
                motivos=list(c.get("motivos", [])),
            )
        )
    return linhas


@app.get("/api/base")
def api_base():
    """Tudo que já está salvo na base (cache de descrições), pra abrir na UI."""
    linhas = _linhas_da_base()
    return {"linhas": [dataclasses.asdict(d) for d in linhas], "total": len(linhas)}


@app.get("/api/base/planilha")
def api_base_planilha():
    """Baixa a base inteira já no formato Pasta1 (Catálogo Siscomex)."""
    destino = exportar_xlsx(_linhas_da_base(), "base_descricoes.xlsx")
    return FileResponse(
        destino,
        filename="base_descricoes.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/api/adicionar")
async def api_adicionar(request: Request, ia: bool = Query(False)):
    """Adiciona UM código à base: busca no catálogo/site, compõe e (se IA) salva no
    cache. marca='raybestos' cobre o catálogo (agnóstico) e o fallback do site."""
    body = await request.json()
    codigo = (body.get("codigo") or "").strip()
    if not codigo:
        return JSONResponse({"erro": "informe um código"}, status_code=400)
    item = ItemInvoice(codigo=codigo, qtd_shipped=0, marca="raybestos")
    spec = buscar_specs(item)
    desc = compor(item, spec, usar_llm=ia)
    desc.qtd_shipped = ""  # base: não é embarque
    desc.origem = ""
    return dataclasses.asdict(desc)
