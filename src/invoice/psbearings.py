"""Parser do invoice PS Bearings MFG (proforma). Layout tabular limpo:

    Type / Description / Quantity / Unit Price(USD) / Total Amount(USD)

Ex.:  PS9002 \\n One Way Clutches \\n 300 \\n US$9.00 \\n US$2,700.00

Fabricante chinês; não há país de origem por item (entra pelo Padrão/manual).
Extração 100% determinística.
"""
from __future__ import annotations

import re

from src.dominio import ItemInvoice
from src.invoice.base import registrar

_INT = re.compile(r"^\d+$")
_CODE = re.compile(r"^[A-Z0-9][A-Z0-9\-]*$")


class PsBearingsParser:
    nome = "psbearings"

    def detectar(self, texto: str) -> bool:
        t = texto.lower()
        return "ps bearings mfg" in t or "psbearings.com" in t

    def extrair(self, paginas: list[str], pdf=None) -> list[ItemInvoice]:
        itens: list[ItemInvoice] = []
        for n_pagina, texto in enumerate(paginas, 1):
            linhas = [ln.strip() for ln in texto.splitlines()]
            i = 0
            while i + 4 < len(linhas):
                if (
                    _CODE.match(linhas[i]) and len(linhas[i]) >= 4   # código
                    and linhas[i + 1] and not _INT.match(linhas[i + 1])  # descrição (texto)
                    and _INT.match(linhas[i + 2])                    # quantidade
                    and linhas[i + 3].startswith("US$")              # unit price
                    and linhas[i + 4].startswith("US$")              # total
                ):
                    itens.append(ItemInvoice(
                        codigo=linhas[i],
                        qtd_shipped=int(linhas[i + 2]),
                        descricao_invoice=linhas[i + 1],
                        marca="psbearings",
                        pagina=n_pagina,
                    ))
                    i += 5
                else:
                    i += 1
        return itens


registrar(PsBearingsParser())
