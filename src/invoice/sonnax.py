"""Parser do invoice Sonnax. Células verticais (pymupdf), um item é:

    <código> / <qtd> / <UOM> / <unit price> / <extended> / <ordered> / <BkO>
    / <descrição> / COUNTRY OF ORIGIN: / <origem>

Ex.:  CH-90-16G \\n 1 \\n EA \\n 4.16 \\n 4.16 \\n 1 \\n 0 \\n HUB, IMPELLER \\n
      COUNTRY OF ORIGIN: \\n INDIA

A origem VARIA por item (USA, INDIA, ...), então vale capturar (não dá pra deixar
só no Padrão). Sem origem -> confiança baixa, nunca inventa. Determinístico.
"""
from __future__ import annotations

import re

from src.dominio import ItemInvoice
from src.invoice.base import registrar

_INT = re.compile(r"^\d+$")
_PRECO = re.compile(r"^[\d,]+\.\d{2}$")
_CODE = re.compile(r"^[A-Z0-9][A-Z0-9\-]*$")
_UOM = re.compile(r"^[A-Z]{1,4}$")


class SonnaxParser:
    nome = "sonnax"

    def detectar(self, texto: str) -> bool:
        return "sonnax" in texto.lower()

    def extrair(self, paginas: list[str]) -> list[ItemInvoice]:
        itens: list[ItemInvoice] = []
        for n_pagina, texto in enumerate(paginas, 1):
            linhas = [ln.strip() for ln in texto.splitlines()]
            i = 0
            while i + 5 < len(linhas):
                if not (
                    _CODE.match(linhas[i]) and len(linhas[i]) >= 3   # código
                    and _INT.match(linhas[i + 1])                    # qtd (shipped)
                    and _UOM.match(linhas[i + 2])                    # UOM (EA, C, ...)
                    and _PRECO.match(linhas[i + 3])                  # unit price
                    and _PRECO.match(linhas[i + 4])                  # extended
                ):
                    i += 1
                    continue

                janela = linhas[i + 5 : i + 14]
                origem = ""
                for k, ln in enumerate(janela):
                    if ln.startswith("COUNTRY OF ORIGIN") and k + 1 < len(janela):
                        origem = janela[k + 1].strip()
                        break
                descricao = linhas[i + 7].strip() if i + 7 < len(linhas) else ""

                item = ItemInvoice(
                    codigo=linhas[i],
                    qtd_shipped=int(linhas[i + 1]),
                    qtd_ordered=int(linhas[i + 5]) if _INT.match(linhas[i + 5]) else 0,
                    origem=origem,
                    descricao_invoice=descricao,
                    marca="sonnax",
                    pagina=n_pagina,
                )
                if not origem:
                    item.problemas = ["origem (COUNTRY OF ORIGIN) não encontrada"]
                    item.confianca = "baixa"
                itens.append(item)
                i += 8
        return itens


registrar(SonnaxParser())
