"""Orquestrador: invoice (PDF) -> itens -> specs -> descrição -> CADASTRO (Produto).

Mudança de centro: a saída do pipeline não é mais "uma descrição solta" — ela faz
MERGE no cadastro do produto (src/produto.py), preservando os campos manuais. O
catálogo de produtos é o que persiste; a descrição DUIMP é um campo dele.

    1. ler PDF                       (extracao)
    2. detectar o parser do invoice  (invoice.base)
    3. extrair itens                 (parser do fornecedor — determinístico)
    4. p/ cada item:
         - já no cadastro? usa (não recompõe — protege a edição manual)
         - senão: busca spec -> compõe descrição -> upsert no cadastro

`processar_stream` emite item a item (a UI mostra progresso ao vivo);
`processar` acumula num Resultado (CLI).
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import src.invoice  # noqa: F401  (importar registra os parsers)
from src import descricao as descricao_mod
from src import produto as produto_mod
from src.dominio import ItemInvoice
from src.extracao import ler_paginas, texto_completo
from src.invoice.base import detectar_parser
from src.produto import Produto
from src.specs import buscar_specs


@dataclass
class Resultado:
    parser: str
    produtos: list[Produto] = field(default_factory=list)
    fila_revisao: list[Produto] = field(default_factory=list)


def obter_ou_compor(
    item: ItemInvoice, templates: list[dict], usar_llm: bool = True, forcar: bool = False
) -> Produto:
    """Coração da ligação pipeline->cadastro. Se o código já está no cadastro com
    descrição, devolve como está (não recompõe). Senão, busca spec, compõe e faz
    upsert. `forcar=True` recompõe mesmo já existindo (ação explícita de regerar)."""
    existente = produto_mod.obter(item.codigo)
    if existente is not None and existente.desc_sisc and not forcar:
        return existente

    spec = buscar_specs(item)
    desc = descricao_mod.compor(item, spec, templates, usar_llm=usar_llm, usar_cache=False)
    return produto_mod.upsert_de_descricao(item, spec, desc)


def processar_stream(
    pdf: str | Path, limite: int | None = None, usar_llm: bool = True, forcar: bool = False
) -> Iterator[tuple[str, Any]]:
    """Eventos: ("inicio", {total, parser}) -> ("item", Produto)* -> ("fim", {total}).
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
        yield ("item", obter_ou_compor(item, templates, usar_llm=usar_llm, forcar=forcar))
    yield ("fim", {"total": len(itens)})


def processar(
    pdf: str | Path, limite: int | None = None, usar_llm: bool = True, forcar: bool = False
) -> Resultado:
    parser_nome = ""
    produtos: list[Produto] = []
    for tipo, payload in processar_stream(pdf, limite=limite, usar_llm=usar_llm, forcar=forcar):
        if tipo == "erro":
            raise ValueError(f"{payload['msg']} Cadastrar um adapter novo em src/invoice/.")
        if tipo == "inicio":
            parser_nome = payload["parser"]
        elif tipo == "item":
            produtos.append(payload)
    fila = [p for p in produtos if produto_mod.incompleto(p)]
    return Resultado(parser=parser_nome, produtos=produtos, fila_revisao=fila)
