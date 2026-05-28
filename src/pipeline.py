"""Orquestrador: invoice (PDF) -> itens -> specs -> descrições DUIMP.

Espelha o pensamento do chat_roger: cada etapa isolada, o determinístico
(extração) fica determinístico, e o que não dá pra confirmar vira fila de revisão.

    1. ler PDF                       (extracao)
    2. detectar o parser do invoice  (invoice.base)
    3. extrair itens                 (parser do fornecedor — determinístico)
    4. p/ cada item: buscar spec     (specs — cache -> site)
    5. compor a descrição DUIMP      (descricao — template + LLM/fallback)

`processar_stream` emite item a item (a UI mostra progresso ao vivo);
`processar` acumula tudo num Resultado (CLI).
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import src.invoice  # noqa: F401  (importar registra os parsers)
from src import descricao as descricao_mod
from src.dominio import DescricaoDUIMP, ItemInvoice
from src.extracao import ler_paginas, texto_completo
from src.invoice.base import detectar_parser
from src.specs import buscar_specs


@dataclass
class Resultado:
    parser: str
    descricoes: list[DescricaoDUIMP] = field(default_factory=list)
    fila_revisao: list[DescricaoDUIMP] = field(default_factory=list)


def processar_stream(
    pdf: str | Path, limite: int | None = None, usar_llm: bool = True
) -> Iterator[tuple[str, Any]]:
    """Eventos: ("inicio", {total, parser}) -> ("item", DescricaoDUIMP)* -> ("fim", {total}).
    Em invoice não reconhecido: ("erro", {msg})."""
    paginas = ler_paginas(pdf)
    parser = detectar_parser(texto_completo(paginas))
    if parser is None:
        yield ("erro", {"msg": "Nenhum parser reconheceu este invoice."})
        return

    itens: list[ItemInvoice] = parser.extrair(paginas)
    if limite:
        itens = itens[:limite]
    templates = descricao_mod.carregar_templates()

    yield ("inicio", {"total": len(itens), "parser": parser.nome})
    for item in itens:
        spec = buscar_specs(item)
        yield ("item", descricao_mod.compor(item, spec, templates, usar_llm=usar_llm))
    yield ("fim", {"total": len(itens)})


def processar(pdf: str | Path, limite: int | None = None, usar_llm: bool = True) -> Resultado:
    parser_nome = ""
    descricoes: list[DescricaoDUIMP] = []
    for tipo, payload in processar_stream(pdf, limite=limite, usar_llm=usar_llm):
        if tipo == "erro":
            raise ValueError(f"{payload['msg']} Cadastrar um adapter novo em src/invoice/.")
        if tipo == "inicio":
            parser_nome = payload["parser"]
        elif tipo == "item":
            descricoes.append(payload)
    fila = [d for d in descricoes if d.precisa_revisao]
    return Resultado(parser=parser_nome, descricoes=descricoes, fila_revisao=fila)
