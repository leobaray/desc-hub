"""Parser do invoice Tri Component. Layout tabular limpo (uma linha por célula):

    LN# / OrderQty / ShipQty / PartID / HTS_CODE / weight / Description / Unit / Ext

Ex.:  1 \\n 145 \\n 145 \\n YO-25-12 \\n 73261911 \\n 0.0074 \\n selo.../seal \\n $4.61 \\n $668.45

Não há país de origem por item neste invoice (o país entra pelo Padrão/manual).
Extração 100% determinística.
"""
from __future__ import annotations

import re

from src.dominio import ItemInvoice
from src.invoice.base import registrar

_INT = re.compile(r"^\d+$")
_CODE = re.compile(r"^[A-Z0-9][A-Z0-9\-]*$")
_HTS = re.compile(r"^\d{6,10}$")
_DEC = re.compile(r"^\d+\.\d+$")


class TricomponentParser:
    nome = "tricomponent"

    def detectar(self, texto: str) -> bool:
        return "tri component" in texto.lower()

    def extrair(self, paginas: list[str]) -> list[ItemInvoice]:
        itens: list[ItemInvoice] = []
        for n_pagina, texto in enumerate(paginas, 1):
            linhas = [ln.strip() for ln in texto.splitlines()]
            i = 0
            while i + 6 < len(linhas):
                if (
                    _INT.match(linhas[i])          # LN#
                    and _INT.match(linhas[i + 1])  # OrderQty
                    and _INT.match(linhas[i + 2])  # ShipQty
                    and _CODE.match(linhas[i + 3]) and len(linhas[i + 3]) >= 3  # PartID
                    and _HTS.match(linhas[i + 4])  # HTS
                    and _DEC.match(linhas[i + 5])  # weight
                ):
                    itens.append(ItemInvoice(
                        codigo=linhas[i + 3],
                        qtd_shipped=int(linhas[i + 2]),
                        qtd_ordered=int(linhas[i + 1]),
                        hts=linhas[i + 4],
                        descricao_invoice=linhas[i + 6],
                        marca="tricomponent",
                        pagina=n_pagina,
                    ))
                    i += 7
                else:
                    i += 1
        return itens


registrar(TricomponentParser())
