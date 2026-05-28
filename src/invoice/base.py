"""Contrato de parser de invoice + registro.

DECISÃO DE ARQUITETURA: "quem emitiu o invoice" != "marca do produto" !=
"qual site tem a spec". Um mesmo invoice (ex.: Gearbox) traz itens Raybestos,
Allomatic e Steel Parts misturados. Por isso:

  - ParserInvoice  -> keyed pelo LAYOUT do invoice (detecta pelo cabeçalho).
  - cada ItemInvoice carrega `marca`, resolvida por código/linha.
  - a busca de spec (src/specs.py) é keyed pela MARCA, não pelo invoice.

Adicionar fornecedor = criar uma classe que satisfaz ParserInvoice e chamar
`registrar(...)` no fim do módulo (ver src/invoice/gearbox.py de referência).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.dominio import ItemInvoice


@runtime_checkable
class ParserInvoice(Protocol):
    nome: str

    def detectar(self, texto: str) -> bool:
        """True se este parser reconhece o layout (pelo cabeçalho do invoice)."""
        ...

    def extrair(self, paginas: list[str]) -> list[ItemInvoice]:
        """Extrai os itens de forma determinística (regex/parser, sem LLM)."""
        ...


_REGISTRO: list[ParserInvoice] = []


def registrar(parser: ParserInvoice) -> ParserInvoice:
    _REGISTRO.append(parser)
    return parser


def detectar_parser(texto: str) -> ParserInvoice | None:
    for p in _REGISTRO:
        try:
            if p.detectar(texto):
                return p
        except Exception:
            continue
    return None


def parsers_registrados() -> list[ParserInvoice]:
    return list(_REGISTRO)
