"""Parser do invoice Gearbox (Raybestos Powertrain / Allomatic / Steel Parts Mfg).

Parser de REFERÊNCIA — molde pros outros fornecedores. Extração 100%
determinística.

O pymupdf devolve cada CÉLULA da tabela numa linha separada, então um item é uma
sequência vertical:

    <ordered>
    <shipped>            <- é esse que a gente quer (o que chegou)
    <back_ordered>
    <CÓDIGO>
    <unit_price>
    <ext_price>
    <descrição>
    HTS CODE: ...
    ORIGIN: ...           <- é esse (país de origem), NÃO o "Made in"
    Made in: ...
    Item Description: ...
    Line Vol (Cu In): ...

Quando origem/descrição não aparecem, marca confiança 'baixa' e registra o
problema — não inventa.

TODO: o invoice mistura marcas (Raybestos/Allomatic/Steel Parts). Hoje marca tudo
como 'raybestos' (e mesmo códigos numéricos costumam existir no site da Raybestos).
"""
from __future__ import annotations

import re

from src.dominio import ItemInvoice
from src.invoice.base import registrar

_INT = re.compile(r"^\d+$")
_PRECO = re.compile(r"^[\d,]+\.\d{2}$")
_CODE = re.compile(r"^[A-Z0-9][A-Z0-9\-]*$")
_IGNORAR_DESC = ("HTS CODE:", "ORIGIN:", "Made in:", "Item Description:", "Line Vol", "** Totals")


class GearboxParser:
    nome = "gearbox"

    def detectar(self, texto: str) -> bool:
        t = texto.lower()
        return "raybestos powertrain" in t or "gearbox" in t

    def extrair(self, paginas: list[str]) -> list[ItemInvoice]:
        itens: list[ItemInvoice] = []
        for n_pagina, texto in enumerate(paginas, 1):
            linhas = [ln.strip() for ln in texto.splitlines()]
            i = 0
            while i + 5 < len(linhas):
                if not self._inicio_item(linhas, i):
                    i += 1
                    continue
                janela = linhas[i + 6 : i + 18]  # contexto até a descrição/origem/hts
                origem = self._campo(janela, "ORIGIN:")
                descricao = self._descricao(janela)

                item = ItemInvoice(
                    codigo=linhas[i + 3],
                    qtd_shipped=int(linhas[i + 1]),
                    qtd_ordered=int(linhas[i]),
                    qtd_backordered=int(linhas[i + 2]),
                    origem=origem,
                    hts=self._campo(janela, "HTS CODE:"),
                    descricao_invoice=descricao,
                    marca="raybestos",
                    pagina=n_pagina,
                )
                problemas: list[str] = []
                if not origem:
                    problemas.append("origem (ORIGIN) não encontrada")
                if not descricao:
                    problemas.append("descrição do item não encontrada")
                if problemas:
                    item.problemas = problemas
                    item.confianca = "baixa"
                itens.append(item)
                i += 6
        return itens

    @staticmethod
    def _inicio_item(linhas: list[str], i: int) -> bool:
        return bool(
            _INT.match(linhas[i])
            and _INT.match(linhas[i + 1])
            and _INT.match(linhas[i + 2])
            and len(linhas[i + 3]) >= 3
            and _CODE.match(linhas[i + 3])
            and _PRECO.match(linhas[i + 4])
            and _PRECO.match(linhas[i + 5])
        )

    @staticmethod
    def _campo(janela: list[str], prefixo: str) -> str:
        for ln in janela:
            if ln.startswith(prefixo):
                return ln[len(prefixo):].strip()
        return ""

    @staticmethod
    def _descricao(janela: list[str]) -> str:
        for ln in janela:
            if ln and not ln.startswith(_IGNORAR_DESC):
                return ln
        return ""


registrar(GearboxParser())
