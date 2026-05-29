"""Padrões nível-declaração — valores que são o MESMO pra (quase) todo item.

Alguns campos da planilha não variam por produto: o `Fabric/Revend` (campo Siscomex
"Fabricante/Revendedor") e, em geral, o `País de origem`. Não faz sentido digitar por
item nem deixar em branco. Você define uma vez aqui; na exportação cada linha recebe o
valor (src/saida.py) e um produto pode sobrescrever (ex.: um item de país diferente).
Setar o padrão também tira esses campos da conta do "incompleto" (src/produto.py).
"""
from __future__ import annotations

from src import db

# Quais campos aceitam padrão global. Manter curto e explícito.
PADROES = ("pais_origem", "fabric_revend")

_cache: dict | None = None


def obter() -> dict:
    """Padrões atuais (cacheado em memória). Sempre devolve todas as chaves de PADROES."""
    global _cache
    if _cache is None:
        db.inicializar()
        with db.conectar() as conn:
            rows = conn.execute("SELECT chave, valor FROM configuracoes").fetchall()
        salvos = {r["chave"]: r["valor"] for r in rows}
        _cache = {k: salvos.get(k, "") for k in PADROES}
    return dict(_cache)


def valor(chave: str) -> str:
    return (obter().get(chave) or "").strip()


def salvar(valores: dict) -> dict:
    global _cache
    db.inicializar()
    with db.conectar() as conn:
        for k, v in valores.items():
            if k in PADROES:
                conn.execute(
                    "INSERT INTO configuracoes (chave, valor) VALUES (?, ?) "
                    "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                    (k, "" if v is None else str(v).strip()),
                )
    _cache = None
    return obter()
