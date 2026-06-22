"""Banco local (SQLite) — a fundação do cadastro de produtos.

O centro do sistema deixou de ser "o pipeline que cospe descrição" e passou a ser
o REGISTRO do produto (cadastro rico, ~3k códigos). Esse cadastro mora aqui.

Por que SQLite: um arquivo só (data/app.db), sem servidor, robusto pra milhares de
registros + edição + consulta ("só incompletos", busca), e portátil. WAL ligado
pra leitura e escrita conviverem sob o servidor web.

Duas tabelas:
  produto  -> a ficha de cada código (todos os campos da planilha completa)
  planilha -> histórico de planilhas exportadas/salvas (nome, tipo, códigos)
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from src.config import settings

# Colunas da tabela produto, na ordem do domínio. TEXT em tudo de propósito: é um
# catálogo/planilha (fidelidade ao que o humano digita), não uma engine de cálculo.
_COLUNAS_PRODUTO = [
    "codigo",                # PK — código do produto (CódigoFabricante, ex.: RGPZ-278)
    "fabricante",            # marca (raybestos/allomatic/...)
    # --- bloco DUIMP (vira a planilha DUIMP) ---
    "cod_ss",                # código interno de vocês
    "cod_sisc",              # código do Catálogo de Produto Siscomex
    "peso",
    "cclasstrib",            # default "1"
    "medida",
    "ncm",
    "desc_sisc",             # a descrição DUIMP (o que o pipeline já gera)
    "nve_materia_prima",
    "nve_processo",
    "nve_acabamento",
    "pais_origem",
    "fabric_revend",         # Siscomex "Fabricante/Revendedor" (≠ revenda_uso_interno)
    # --- bloco extra (só na planilha completa) ---
    "descricao",             # descrição geral/comercial (manual; != desc_sisc)
    "un_medida_entrada",
    "qtd_embalagem_entrada",
    "un_medida_saida",
    "qtd_embalagem_saida",
    "localizacao_estoque",
    "aplicacoes",            # aplicações / informações técnicas
    "veiculos",
    "caracteristicas",       # opcional
    "revenda_uso_interno",   # classificação interna (Revenda / Uso interno)
    "imagem",                # nome do arquivo se houver (data/imagens/{codigo}.jpg)
    # --- metadados (não vão pra planilha) ---
    "template",
    "ncm_sugerida",
    "fonte_url",
    "motivos",               # JSON list — por que a descrição precisou de atenção
    "criado_em",
    "atualizado_em",
]

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS produto (
    {", ".join(f"{c} TEXT" for c in _COLUNAS_PRODUTO)},
    PRIMARY KEY (codigo)
);

CREATE TABLE IF NOT EXISTS planilha (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    tipo        TEXT NOT NULL,          -- 'duimp' | 'completa'
    codigos     TEXT NOT NULL,          -- JSON list dos códigos exportados
    total       INTEGER NOT NULL DEFAULT 0,
    arquivo     TEXT NOT NULL DEFAULT '',  -- caminho do xlsx salvo em disco
    criada_em   TEXT NOT NULL
);

-- Padrões nível-declaração (mesmo valor pra todos os itens): pais_origem, fabric_revend.
CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL DEFAULT ''
);

-- Tabela de preços dos conversores de torque (área separada do cadastro DUIMP).
-- TEXT nos valores de propósito: a planilha de origem mistura moeda com texto livre
-- ("2.800 / FREE 3.500", "Amarok 4.000,00") e isso não pode ser perdido.
CREATE TABLE IF NOT EXISTS conversor (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    modelo         TEXT NOT NULL,          -- modelo da transmissão (ex.: 6L80, ZF8HP45)
    preco_de       TEXT NOT NULL DEFAULT '',
    preco_ate      TEXT NOT NULL DEFAULT '',
    venda_impostos TEXT NOT NULL DEFAULT '',
    anotacoes      TEXT NOT NULL DEFAULT '',
    atualizado_em  TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_produto_fabricante ON produto(fabricante);
"""


def _conn() -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    """Abre conexão, commita no sucesso, faz rollback no erro, sempre fecha."""
    conn = _conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_INICIALIZADO = False


def inicializar() -> None:
    """Cria as tabelas se não existirem e auto-migra colunas novas. Idempotente."""
    global _INICIALIZADO
    if _INICIALIZADO:
        return
    with conectar() as conn:
        conn.executescript(_SCHEMA)
        # auto-migração: bancos antigos ganham colunas novas sem precisar recriar
        existentes = {r["name"] for r in conn.execute("PRAGMA table_info(produto)")}
        for col in _COLUNAS_PRODUTO:
            if col not in existentes:
                conn.execute(f"ALTER TABLE produto ADD COLUMN {col} TEXT DEFAULT ''")
    _INICIALIZADO = True


def colunas_produto() -> list[str]:
    return list(_COLUNAS_PRODUTO)
