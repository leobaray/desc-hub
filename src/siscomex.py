"""Integração com o Catálogo de Produtos do Siscomex (Portal Único).

Por enquanto: importar o EXPORT do catálogo. O Portal permite exportar todo o
catálogo da empresa num JSON (dentro de um .zip). Cada produto traz:
  - codigosInterno : os NOSSOS códigos (CódigoFabricante) — a chave do cruzamento
  - codigo         : o código do produto no Siscomex
  - descricao      : a descrição DUIMP oficial, já registrada
  - denominacao    : o nome comercial
  - ncm, situacao, modalidade, versao, atributos*

A gente cruza por codigoInterno e copia o oficial pro cadastro.

Decidido com o Leonardo:
  - cod_sisc, desc_sisc e descrição (denominação): o Siscomex MANDA (sobrescreve até
    palpite do pipeline) — é o dado oficial registrado.
  - NCM: NÃO é copiado. A classificação vem do trabalho de família->NCM da
    contabilidade (e pode mudar até no próprio Siscomex).
  - Conflito (mesmo código nosso -> 2 produtos Siscomex): pulado e reportado.
  - atributos (ATT_xxxx): ficam pra um 2º passo (precisam do dicionário de atributos).

(O fluxo de API — autenticar/exportar/incluir via certificado — entra aqui depois.)

    python -m src.siscomex caminho/CATALOGO_PRODUTOS_*.zip
"""
from __future__ import annotations

import io
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from src import produto as produto_mod

FONTE = "siscomex"


def carregar_export(origem: str | Path | bytes) -> list[dict]:
    """Aceita o .zip (lê o .json de dentro), o .json direto, ou bytes."""
    if isinstance(origem, (bytes, bytearray)):
        dados = bytes(origem)
    else:
        dados = Path(origem).read_bytes()
    if dados[:2] == b"PK":  # assinatura de zip
        with zipfile.ZipFile(io.BytesIO(dados)) as zf:
            nome = next(n for n in zf.namelist() if n.lower().endswith(".json"))
            dados = zf.read(nome)
    return json.loads(dados.decode("utf-8"))


def _indexar_por_interno(prods: list[dict]) -> tuple[dict[str, list[dict]], int]:
    por_interno: dict[str, list[dict]] = defaultdict(list)
    sem_interno = 0
    for p in prods:
        cis = p.get("codigosInterno") or []
        if not cis:
            sem_interno += 1
        for ci in cis:
            por_interno[str(ci).strip()].append(p)
    return por_interno, sem_interno


def importar_export(origem: str | Path | bytes) -> dict:
    """Cruza o export do Siscomex com o cadastro e copia o oficial (menos NCM)."""
    prods = carregar_export(origem)
    por_interno, sem_interno = _indexar_por_interno(prods)
    nossos = {p.codigo for p in produto_mod.listar()}

    atualizados = 0
    conflitos: list[dict] = []
    campos_set: Counter = Counter()

    for ci, ps in por_interno.items():
        if ci not in nossos:
            continue
        if len(ps) > 1:  # mesmo código nosso -> vários produtos Siscomex: não chuta
            conflitos.append({"codigo": ci, "siscomex": [s.get("codigo") for s in ps]})
            continue
        s = ps[0]
        campos: dict[str, str] = {}
        cod_sisc = str(s.get("codigo") or "").strip()
        if cod_sisc:
            campos["cod_sisc"] = cod_sisc
        desc = (s.get("descricao") or "").strip()
        if desc:
            campos["desc_sisc"] = desc          # descrição DUIMP oficial (Siscomex manda)
        denom = (s.get("denominacao") or "").strip()
        if denom:
            campos["descricao"] = denom         # nome comercial
        # NCM: deliberadamente NÃO copiado.
        if campos:
            campos["fonte_url"] = FONTE
            produto_mod.atualizar_campos(ci, campos)
            atualizados += 1
            for k in campos:
                campos_set[k] += 1

    return {
        "produtos_no_export": len(prods),
        "casaram_atualizados": atualizados,
        "conflitos": conflitos,
        "orfaos_no_export": sorted(set(por_interno) - nossos),
        "sem_codigo_interno": sem_interno,
        "campos_preenchidos": dict(campos_set),
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("uso: python -m src.siscomex caminho/CATALOGO_PRODUTOS_*.zip")
        raise SystemExit(2)
    res = importar_export(sys.argv[1])
    res["conflitos"] = f"{len(res['conflitos'])} (ver lista)"
    res["orfaos_no_export"] = f"{len(res['orfaos_no_export'])}"
    print(res)
