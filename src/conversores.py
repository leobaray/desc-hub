"""Preços dos conversores de torque — área separada do cadastro DUIMP.

A equipe de vendas mantinha os preços numa planilha de rede (modelo da transmissão,
faixa do reparo DE/ATÉ, venda + impostos, anotações); aqui isso vira uma tabela no
banco com busca instantânea e edição campo a campo na tela.

Fidelidade ao que o humano digita (mesmo princípio do cadastro): os valores são TEXT
porque o preço mistura moeda com texto livre ("2.800 / FREE 3.500",
"Amarok 4.000,00", "21A e 21B=2.250,00 ...") — nada disso pode ser normalizado fora.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, fields
from datetime import datetime

from src import db

CAMPOS_EDITAVEIS = ("modelo", "preco_de", "preco_ate", "venda_impostos", "anotacoes")


@dataclass
class Conversor:
    id: int | None = None
    modelo: str = ""
    preco_de: str = ""
    preco_ate: str = ""
    venda_impostos: str = ""
    anotacoes: str = ""
    atualizado_em: str = ""


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def to_dict(c: Conversor) -> dict:
    return asdict(c)


def _de_row(r) -> Conversor:
    nomes = {f.name for f in fields(Conversor)}
    return Conversor(**{k: r[k] for k in r.keys() if k in nomes})


def _sem_acento(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if not unicodedata.combining(ch))


# --- repositório -------------------------------------------------------------
def listar(busca: str = "") -> list[Conversor]:
    """Todos os conversores, ordenados por modelo. A busca olha TODOS os campos
    (modelo, preços, venda, anotações) e é tolerante a maiúscula, acento e
    separador: "6l80", "6L-80", "pistao" e "PISTÃO" acham a mesma linha."""
    db.inicializar()
    with db.conectar() as conn:
        rows = conn.execute("SELECT * FROM conversor ORDER BY modelo COLLATE NOCASE").fetchall()
    itens = [_de_row(r) for r in rows]
    q = _sem_acento((busca or "").strip().lower())
    if not q:
        return itens

    def compacta(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s)

    qc = compacta(q)

    def bate(c: Conversor) -> bool:
        alvo = _sem_acento(
            f"{c.modelo} {c.preco_de} {c.preco_ate} {c.venda_impostos} {c.anotacoes}".lower()
        )
        return q in alvo or (bool(qc) and qc in compacta(alvo))

    return [c for c in itens if bate(c)]


# Revisão da tabela: incrementa a cada escrita. A UI dos outros usuários consulta
# esse número de tempos em tempos e recarrega sozinha quando muda (sem F5).
_CHAVE_REV = "conversores_rev"


def _rev_bump(conn) -> None:
    conn.execute(
        "INSERT INTO configuracoes (chave, valor) VALUES (?, '1') "
        "ON CONFLICT(chave) DO UPDATE SET valor = CAST(valor AS INTEGER) + 1",
        (_CHAVE_REV,),
    )


def rev() -> int:
    db.inicializar()
    with db.conectar() as conn:
        r = conn.execute("SELECT valor FROM configuracoes WHERE chave = ?", (_CHAVE_REV,)).fetchone()
    try:
        return int(r["valor"]) if r else 0
    except (ValueError, TypeError):
        return 0


def obter(cid: int) -> Conversor | None:
    db.inicializar()
    with db.conectar() as conn:
        r = conn.execute("SELECT * FROM conversor WHERE id = ?", (cid,)).fetchone()
    return _de_row(r) if r else None


def criar(campos: dict) -> Conversor:
    c = Conversor(**{k: str(campos.get(k) or "").strip() for k in CAMPOS_EDITAVEIS})
    if not c.modelo:
        raise ValueError("informe o modelo da transmissão")
    c.atualizado_em = _agora()
    db.inicializar()
    with db.conectar() as conn:
        cur = conn.execute(
            "INSERT INTO conversor (modelo, preco_de, preco_ate, venda_impostos, anotacoes, atualizado_em) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (c.modelo, c.preco_de, c.preco_ate, c.venda_impostos, c.anotacoes, c.atualizado_em),
        )
        c.id = cur.lastrowid
        _rev_bump(conn)
    return c


def atualizar(cid: int, campos: dict) -> Conversor | None:
    c = obter(cid)
    if c is None:
        return None
    for k in CAMPOS_EDITAVEIS:
        if k in campos:
            setattr(c, k, str(campos.get(k) or "").strip())
    if not c.modelo:
        raise ValueError("o modelo não pode ficar vazio")
    c.atualizado_em = _agora()
    with db.conectar() as conn:
        conn.execute(
            "UPDATE conversor SET modelo=?, preco_de=?, preco_ate=?, venda_impostos=?, "
            "anotacoes=?, atualizado_em=? WHERE id=?",
            (c.modelo, c.preco_de, c.preco_ate, c.venda_impostos, c.anotacoes, c.atualizado_em, cid),
        )
        _rev_bump(conn)
    return c


def remover(cid: int) -> bool:
    db.inicializar()
    with db.conectar() as conn:
        cur = conn.execute("DELETE FROM conversor WHERE id = ?", (cid,))
        if cur.rowcount:
            _rev_bump(conn)
        return cur.rowcount > 0


def total() -> int:
    db.inicializar()
    with db.conectar() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM conversor").fetchone()["n"]
