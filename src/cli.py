"""CLI do pipeline.

    python -m src.cli --pdf "INVOICE RAYBESTOS.PDF"
    python -m src.cli --pdf "INVOICE RAYBESTOS.PDF" --limite 6 --ia

Lê o invoice, extrai os itens, faz upsert no cadastro (Produto) e exporta a planilha
DUIMP. Mostra quantos produtos ficaram incompletos (laranja) e por quê.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from src import produto as produto_mod
from src import saida
from src.config import settings
from src.pipeline import processar


def main() -> int:
    ap = argparse.ArgumentParser(description="Invoice -> cadastro -> planilha DUIMP")
    ap.add_argument("--pdf", required=True, help="Caminho do invoice em PDF")
    ap.add_argument("--saida", default="descricoes.xlsx", help="Nome do xlsx de saída (DUIMP)")
    ap.add_argument(
        "--limite", type=int, default=None, help="Processar só os N primeiros itens (teste)"
    )
    ap.add_argument("--ia", action="store_true", help="Redigir descrições com o LLM (mais lento)")
    args = ap.parse_args()

    res = processar(args.pdf, limite=args.limite, usar_llm=args.ia)
    destino = saida.exportar(res.produtos, "duimp", settings.saida_dir / args.saida)

    print(f"[*] parser do invoice : {res.parser}")
    print(f"[*] produtos no lote  : {len(res.produtos)}")
    print(f"[*] incompletos       : {len(res.fila_revisao)}")
    print(f"[*] planilha DUIMP    : {destino}")

    if res.fila_revisao:
        print("\nIncompletos (primeiros 20) — campos faltando:")
        for p in res.fila_revisao[:20]:
            falta = ", ".join(produto_mod.campos_faltando(p)[:5])
            print(f"  - {p.codigo}: {falta} …")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
