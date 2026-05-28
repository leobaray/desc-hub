"""Store de imagens dos produtos: uma imagem por código em data/imagens/{codigo}.jpg.

Pro cliente, o que importa é a imagem aparecer na pasta `imagens/` ao lado da planilha
(jpg nomeado pelo código). Internamente guardamos tudo aqui; na exportação completa a
gente monta a pasta a partir deste store.

V1 aceita o upload como veio e grava com extensão .jpg (a UI pede jpg). Conversão de
PNG->JPG fica pra depois (exigiria Pillow; hoje não está nas deps).
"""
from __future__ import annotations

import re
from pathlib import Path

from src.config import settings


def _safe(codigo: str) -> str:
    """Código -> nome de arquivo seguro. Part numbers reais (RGPZ-278, 512568) já são
    seguros; isso só blinda contra algum caractere estranho."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", (codigo or "").strip()) or "_"


def nome_arquivo(codigo: str) -> str:
    return f"{_safe(codigo)}.jpg"


def caminho(codigo: str) -> Path:
    return settings.imagens_dir / nome_arquivo(codigo)


def tem(codigo: str) -> bool:
    return caminho(codigo).exists()


def salvar(codigo: str, dados: bytes) -> Path:
    settings.imagens_dir.mkdir(parents=True, exist_ok=True)
    destino = caminho(codigo)
    destino.write_bytes(dados)
    return destino


def remover(codigo: str) -> bool:
    p = caminho(codigo)
    if p.exists():
        p.unlink()
        return True
    return False
