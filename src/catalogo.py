"""Índice local dos catálogos Raybestos + Allomatic (PDF) — fonte PRIMÁRIA de specs.

Por que: offline, instantâneo, cobre Allomatic + SKUs que o site não acha
(ex.: FRMHYUND07) e resolve o código→marca (o índice tem os códigos das duas marcas).

Cada página de produto tem um cabeçalho (make / transmissão / anos) ACIMA de uma
tabela `Part No. | Description | Thick | Qty. | Year | Ref# | OE# | Notes`. Linhas
com Part No. vazio são continuação (merge). Linhas-rótulo ("Modules", "Friction
Plates", "Steel Plates", "Filters…") só trocam a categoria corrente. Para filtros,
material e nº de parafusos vêm do Notes ("All Plastic, 12 Pan Bolts") e o código da
junta é a linha de "Gasket -" logo abaixo.

    python -m src.catalogo        # (re)constrói data/catalogo/index.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.config import settings

_CATALOGOS = [
    "catalogos/raybestos_rpt_2026.pdf",  # Raybestos — catálogo principal (ed. 05/2026)
    "catalogos/allomatic.pdf",           # Allomatic
    # Os abaixo têm layout DIFERENTE do "Part No. | Description | ..." — o parser
    # atual lê os cabeçalhos de aplicação (ex.: "Ford 4R70W") como se fossem código.
    # Guardados pra futuro, FORA do índice (pedem parser próprio):
    #   catalogos/raybestos_torque_converter.pdf  (componentes de conversor de torque)
    #   catalogos/raybestos_friction_specs.pdf    (dimensões: Thickness/Teeth/OD/ID)
    #   catalogos/allomatic_filter_catalog.pdf    (filtros; o RPT já cobria 131/135,
    #     só os 4 que faltavam entram via _FILTROS_EXTRA abaixo — sem parser completo)
]

# Filtros do Allomatic Filter Catalog que o índice (RPT + Allomatic) ainda não tinha.
# Dado extraído À MÃO da fonte (catalogos/allomatic_filter_catalog.pdf) — não é parsing,
# são 4 registros pontuais. junta_ref = código da gaxeta (nitrile 22G, salvo a moldada).
_FILTROS_EXTRA: dict[str, dict] = {
    "515420": {"codigo": "515420", "categoria": "Filters", "descricao": "Filter",
               "aplicacao": "VOLKSWAGEN / AUDI 010, 087, 089, 090 1977-1993",
               "make": "VOLKSWAGEN / AUDI", "anos": "1977-1993",
               "junta_ref": "04G420", "notes": "Round (gaxeta de borracha moldada)",
               "oe": "010-325-421A",
               "catalogo": "catalogos/allomatic_filter_catalog.pdf", "pagina": 72},
    "515490": {"codigo": "515490", "categoria": "Filters", "descricao": "Filter",
               "aplicacao": "CHRYSLER 45RFE, 545RFE, 65RFE, 66RFE, 68RFE (2WD, 4WD) 1999-ON",
               "make": "CHRYSLER", "anos": "1999-ON", "junta_ref": "22G492",
               "oe": "04799662AB, 05179267AC, 4799662, 4799662A, 4799662AB, 5179267AC",
               "catalogo": "catalogos/allomatic_filter_catalog.pdf", "pagina": 9},
    "515492": {"codigo": "515492", "categoria": "Filters", "descricao": "Filter",
               "aplicacao": "CHRYSLER 65RFE, 66RFE (2WD), 68RFE (4WD)",
               "make": "CHRYSLER", "junta_ref": "22G492", "parafusos": "15",
               "oe": "05013470AA, 05013470AB, 05013470AC, 05013470AD, 05013470AE, 4799507",
               "catalogo": "catalogos/allomatic_filter_catalog.pdf", "pagina": 9},
    "515703": {"codigo": "515703", "categoria": "Filters", "descricao": "Filter",
               "aplicacao": "GM 4L60E 1993-ON", "make": "GM", "anos": "1993-ON",
               "junta_ref": "22G700", "parafusos": "16", "notes": "Auxiliary Pump Filter",
               "oe": "24200796, 24208148, 24208835",
               "catalogo": "catalogos/allomatic_filter_catalog.pdf", "pagina": 26},
}
_COLS = ("Part No.", "Description", "Thick", "Qty.", "Year", "Ref#", "OE#", "Notes")
_CATEGORIAS = (
    "Modules", "Friction Plates", "Steel Plates", "Filters", "Bands", "Bushings",
    "Sprags", "Washers", "Pistons", "Gaskets", "Seals", "Bearings", "Snap Rings",
    "Pressure Plates", "Backing Plates", "Apply Plates", "Torque Converter",
)
_RE_ANO = re.compile(r"^\d{4}(?:-\d{4}|-ON|-on)?$")
_RE_MATERIAL = re.compile(r"All (?:Plastic|Metal)", re.I)
_RE_PARAFUSOS = re.compile(r"(\d+)\s*Pan Bolts", re.I)

_INDEX_PATH = settings.cache_dir.parent / "catalogo" / "index.json"
_INDEX: dict | None = None


def _limpar(s) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def _cabecalho(page, topo_tabela: float) -> tuple[str, str, str]:
    """Make / transmissão / anos a partir do texto ACIMA da tabela."""
    linhas: list[str] = []
    for b in page.get_text("blocks"):
        y1, txt = b[3], b[4]
        if y1 <= topo_tabela + 2:
            for ln in str(txt).splitlines():
                ln = ln.strip()
                if ln and ln not in _COLS:
                    linhas.append(ln)
    make = linhas[0] if linhas else ""
    anos = next((ln for ln in linhas if _RE_ANO.match(ln)), "")
    transm = " ".join(ln for ln in linhas[1:] if ln != anos)
    return _limpar(make), _limpar(transm), anos


def _maior_tabela(page):
    tabs = page.find_tables()
    if not tabs.tables:
        return None
    return max(tabs.tables, key=lambda t: len(t.rows))


def build_index() -> dict:
    import fitz

    registros: dict[str, dict] = {}
    for nome in _CATALOGOS:
        caminho = Path(nome)
        if not caminho.exists():
            print(f"[!] não encontrei {nome}, pulando")
            continue
        doc = fitz.open(str(caminho))
        total = len(doc)
        print(f"[*] {nome}: {total} páginas")
        for pno in range(total):
            page = doc[pno]
            if "Part No." not in page.get_text("text"):
                continue
            tab = _maior_tabela(page)
            if tab is None:
                continue
            make, transm, anos = _cabecalho(page, tab.bbox[1])
            aplicacao = _limpar(f"{make} {transm} {anos}")

            categoria = ""
            atual: dict | None = None
            filtros_pagina: list[dict] = []
            page_records: list[dict] = []
            for raw in tab.extract():
                cells = [_limpar(c) for c in raw]
                if not cells or cells[0] == "Part No.":
                    continue
                part = cells[0]
                so_primeira = part and not any(cells[1:])

                if so_primeira and any(part.startswith(c) for c in _CATEGORIAS):
                    categoria = part
                    atual = None
                    continue
                if not part:  # continuação: anexa ao registro da linha anterior
                    if atual:
                        if len(cells) > 1 and cells[1]:
                            atual["descricao"] = _limpar(f"{atual['descricao']} {cells[1]}")
                        if len(cells) > 6 and cells[6]:
                            atual["oe"] = _limpar(f"{atual['oe']}, {cells[6]}").strip(", ")
                        if len(cells) > 7 and cells[7]:
                            atual["notes"] = _limpar(f"{atual['notes']} {cells[7]}")
                    continue

                rec = {
                    "codigo": part,
                    "descricao": cells[1] if len(cells) > 1 else "",
                    "thick": cells[2] if len(cells) > 2 else "",
                    "qty": cells[3] if len(cells) > 3 else "",
                    "year": cells[4] if len(cells) > 4 else "",
                    "ref": cells[5] if len(cells) > 5 else "",
                    "oe": cells[6] if len(cells) > 6 else "",
                    "notes": cells[7] if len(cells) > 7 else "",
                    "categoria": categoria,
                    "make": make,
                    "transmissao": transm,
                    "anos": anos,
                    "aplicacao": aplicacao,
                    "catalogo": nome,
                    "pagina": pno + 1,
                }
                atual = rec
                page_records.append(rec)

                # Filtro: material + parafusos do Notes. Junta só entra se um
                # "Gasket -" com o MESMO nº de parafusos aparecer (senão, não tem
                # junta — ex.: 016698 tem 17 bolts, o gasket vizinho tem 18 → não é dele).
                desc_low = rec["descricao"].lower()
                if "filter" in desc_low or categoria.startswith("Filters"):
                    mm = _RE_MATERIAL.search(rec["notes"])
                    if mm:
                        rec["material"] = mm.group(0)
                    mp = _RE_PARAFUSOS.search(rec["notes"])
                    if mp:
                        rec["parafusos"] = mp.group(1)
                if desc_low.startswith("filter"):
                    filtros_pagina.append(rec)
                elif desc_low.startswith("gasket"):
                    mg = _RE_PARAFUSOS.search(rec["notes"])
                    bolts = mg.group(1) if mg else ""
                    for f in reversed(filtros_pagina):
                        if bolts and f.get("parafusos") == bolts and not f.get("junta_ref"):
                            f["junta_ref"] = part
                            break

            # merge no índice: código novo entra; recorrência preenche só campos vazios
            for rec in page_records:
                ex = registros.get(rec["codigo"])
                if ex is None:
                    registros[rec["codigo"]] = rec
                else:
                    for k, v in rec.items():
                        if v and not ex.get(k):
                            ex[k] = v

            if pno and pno % 80 == 0:
                print(f"    ... {nome} pág {pno} | {len(registros)} códigos")
        doc.close()

    # filtros pontuais do Allomatic Filter Catalog (ver _FILTROS_EXTRA): novo entra,
    # existente só preenche campo vazio — mesma regra de merge dos catálogos.
    for cod, rec in _FILTROS_EXTRA.items():
        ex = registros.get(cod)
        if ex is None:
            registros[cod] = dict(rec)
        else:
            for k, v in rec.items():
                if v and not ex.get(k):
                    ex[k] = v

    _INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INDEX_PATH.write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] {len(registros)} códigos -> {_INDEX_PATH}")
    return registros


def carregar_index() -> dict:
    global _INDEX
    if _INDEX is None:
        _INDEX = json.loads(_INDEX_PATH.read_text(encoding="utf-8")) if _INDEX_PATH.exists() else {}
    return _INDEX


# Apelidos: código da invoice (antigo/distribuidor) -> código do catálogo/site.
# Ex.: RCP96-283 foi substituído por RHT96-283 (/friction-clutch-packs/rht96-283-845re).
# Adicione aqui as equivalências que você for descobrindo.
_ALIASES = {"RCP96-283": "RHT96-283"}


def buscar_no_catalogo(codigo: str) -> dict | None:
    idx = carregar_index()
    alvo = _ALIASES.get(codigo) or _ALIASES.get(codigo.upper()) or codigo
    rec = idx.get(alvo) or idx.get(alvo.upper())
    if rec is None and alvo.isdigit():
        # tolera zero à esquerda: cadastro '016699' <-> catálogo '16699'
        rec = idx.get(alvo.lstrip("0")) or idx.get(alvo.zfill(6))
    return rec


if __name__ == "__main__":
    build_index()
