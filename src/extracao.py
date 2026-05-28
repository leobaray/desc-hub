"""Leitura do PDF do invoice -> texto por página. Determinístico (pymupdf), sem LLM."""
from __future__ import annotations

from pathlib import Path


def ler_paginas(caminho: str | Path) -> list[str]:
    import fitz  # pymupdf

    try:
        fitz.TOOLS.mupdf_display_errors(False)
    except Exception:
        pass

    paginas: list[str] = []
    with fitz.open(str(caminho)) as doc:
        for pagina in doc:
            paginas.append(pagina.get_text("text"))
    return paginas


def texto_completo(paginas: list[str]) -> str:
    return "\n".join(paginas)
