"""Acesso ao Cadastro — senha única com hash, pra área não ficar aberta pra qualquer um.

A CONSULTA dos Conversores é da equipe de vendas e fica livre; o Cadastro (DUIMP,
planilhas, padrões) e a ALTERAÇÃO dos conversores (salvar/apagar/importar) pedem uma
senha na primeira vez. O navegador guarda um token e não pergunta de novo.

Como funciona:
  - a senha NUNCA fica em texto plano: só o hash PBKDF2-HMAC-SHA256 (200k iterações,
    salt aleatório), seedado na tabela configuracoes na primeira verificação;
  - acertou a senha -> recebe o token DO DIA: HMAC(segredo, data de hoje). O token
    vence sozinho na virada do dia — no dia seguinte todo mundo loga de novo;
  - as rotas do cadastro exigem o token (header X-Acesso ou query ?acesso=, pros
    <img>/<a download> que não têm header).

Trocar a senha:  python -m src.acesso "NovaSenha"
(também troca o segredo — derruba os tokens do dia na hora)
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
from datetime import date

from src import db

# Hash da senha inicial (definida pelo Leonardo). Só o hash vive no código.
_HASH_INICIAL = "pbkdf2$200000$384500febb742c549b92f7b82e4c29bf$4e5b71526af39ef7e66890f3d1cc6decfd2b70ac629a66a3c735f9fffb0fbb7b"

_CHAVE_HASH = "cadastro_senha_hash"
_CHAVE_SECRET = "cadastro_secret"


def _hash(senha: str, salt: bytes, iters: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, iters)


def _formatar(senha: str) -> str:
    salt = os.urandom(16)
    iters = 200_000
    return f"pbkdf2${iters}${salt.hex()}${_hash(senha, salt, iters).hex()}"


def _confere(senha: str, armazenado: str) -> bool:
    try:
        _, iters, salt_hex, hash_hex = armazenado.split("$")
        calculado = _hash(senha, bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(calculado, bytes.fromhex(hash_hex))
    except (ValueError, TypeError):
        return False


def _ler(conn, chave: str) -> str:
    r = conn.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,)).fetchone()
    return r["valor"] if r else ""


def _gravar(conn, chave: str, valor: str) -> None:
    conn.execute(
        "INSERT INTO configuracoes (chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (chave, valor),
    )


def _token_do_dia(secret_hex: str) -> str:
    """Token derivado da data: vale só hoje, vence sozinho na virada do dia."""
    return hmac.new(bytes.fromhex(secret_hex), date.today().isoformat().encode(), hashlib.sha256).hexdigest()


def verificar(senha: str) -> str | None:
    """Senha certa -> token DO DIA; errada -> None. Seeda hash e segredo na 1ª vez."""
    db.inicializar()
    with db.conectar() as conn:
        armazenado = _ler(conn, _CHAVE_HASH)
        if not armazenado:
            armazenado = _HASH_INICIAL
            _gravar(conn, _CHAVE_HASH, armazenado)
        if not _confere(senha, armazenado):
            return None
        secret = _ler(conn, _CHAVE_SECRET)
        if not secret:
            secret = os.urandom(32).hex()
            _gravar(conn, _CHAVE_SECRET, secret)
        return _token_do_dia(secret)


def token_valido(token: str) -> bool:
    if not token:
        return False
    db.inicializar()
    with db.conectar() as conn:
        secret = _ler(conn, _CHAVE_SECRET)
    return bool(secret) and hmac.compare_digest(token, _token_do_dia(secret))


def trocar_senha(nova: str) -> None:
    """Grava o hash da senha nova e troca o segredo (derruba os tokens do dia)."""
    if not nova or len(nova) < 6:
        raise ValueError("a senha precisa de pelo menos 6 caracteres")
    db.inicializar()
    with db.conectar() as conn:
        _gravar(conn, _CHAVE_HASH, _formatar(nova))
        conn.execute("DELETE FROM configuracoes WHERE chave IN (?, 'cadastro_token')", (_CHAVE_SECRET,))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('uso: python -m src.acesso "NovaSenha"')
        sys.exit(1)
    trocar_senha(sys.argv[1])
    print("Senha do cadastro trocada. O token antigo foi invalidado.")
