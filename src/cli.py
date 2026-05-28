"""CLI do pipeline.

    python -m src.cli --pdf "INVOICE RAYBESTOS.PDF"
    python -m src.cli --pdf "INVOICE RAYBESTOS.PDF" --limite 6 --ia

Lê o invoice, extrai os itens, monta as descrições DUIMP e exporta a planilha.
Mostra quantos itens precisam de revisão humana (e por quê).
"""
from __future__ import annotations

import argparse

from src.pipeline import processar
from src.saida import exportar_xlsx


def main() -> int:
    ap = argparse.ArgumentParser(description="Invoice -> descrições DUIMP/Siscomex")
    ap.add_argument("--pdf", required=True, help="Caminho do invoice em PDF")
    ap.add_argument("--saida", default="descricoes.xlsx", help="Nome do xlsx de saída")
    ap.add_argument(
        "--limite", type=int, default=None, help="Processar só os N primeiros itens (teste)"
    )
    ap.add_argument("--ia", action="store_true", help="Redigir descrições com o LLM (mais lento)")
    args = ap.parse_args()

    res = processar(args.pdf, limite=args.limite, usar_llm=args.ia)
    destino = exportar_xlsx(res.descricoes, args.saida)

    print(f"[*] parser do invoice : {res.parser}")
    print(f"[*] descrições geradas: {len(res.descricoes)}")
    print(f"[*] precisam revisão  : {len(res.fila_revisao)}")
    print(f"[*] planilha          : {destino}")

    if res.fila_revisao:
        print("\nPra revisar (primeiros 20):")
        for d in res.fila_revisao[:20]:
            print(f"  - {d.codigo}: {'; '.join(d.motivos)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
