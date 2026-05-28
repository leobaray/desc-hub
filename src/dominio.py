"""Tipos do domínio. Três estágios de dado, na ordem do pipeline:

    ItemInvoice    -> o que saiu do PDF (determinístico, pode vir incompleto)
    SpecProduto    -> o que o site do fabricante confirmou sobre o código
    DescricaoDUIMP -> a descrição final (UMA só), pronta pra coluna Descrição do
                      Catálogo de Produtos do Siscomex

Regra-mãe (herdada do chat_roger): o que não dá pra confirmar não é inventado —
é marcado com precisa_revisao e vai pra fila de revisão humana.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Confianca = Literal["alta", "media", "baixa"]


@dataclass
class ItemInvoice:
    """Uma linha do invoice. `qtd_shipped` é o que chegou (não o ordered)."""

    codigo: str
    qtd_shipped: int
    origem: str = ""              # ORIGIN: do invoice (país de origem) — NÃO o "Made in:"
    descricao_invoice: str = ""
    hts: str = ""                 # HTS code do invoice (referência; HTS != NCM)
    marca: str = ""               # marca resolvida (ex.: raybestos) -> escolhe a FonteSpecs
    qtd_ordered: int = 0
    qtd_backordered: int = 0
    pagina: int = 0
    confianca: Confianca = "alta"
    problemas: list[str] = field(default_factory=list)


@dataclass
class SpecProduto:
    """Ficha do produto vinda do site do fabricante (ou do cache).

    `atributos` carrega o que foi raspado: titulo, aplicacao, descricao, e os
    campos da tabela de specs quando existem (material, junta_ref, parafusos)."""

    codigo: str
    marca: str
    encontrado: bool = False
    fonte_url: str = ""
    atributos: dict[str, str] = field(default_factory=dict)
    confianca: Confianca = "baixa"
    revisado: bool = False


@dataclass
class DescricaoDUIMP:
    """Saída final — UMA descrição para a coluna Descrição do Catálogo Siscomex."""

    codigo: str
    descricao: str = ""
    atributos: dict[str, str] = field(default_factory=dict)
    ncm_sugerida: str = ""
    template: str = ""
    qtd_shipped: int = 0
    origem: str = ""
    fonte_url: str = ""
    precisa_revisao: bool = True
    motivos: list[str] = field(default_factory=list)
