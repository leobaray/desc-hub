"""One-shot: aplica a aba CORREÇÃO da contabilidade no cadastro.

Lê data/correcao_trabalho.json (extraído da planilha: só linhas com a coluna
CORREÇÃO preenchida e NÃO laranja — laranja = status "?" ou "Descontinuado").
Regras:
  - ncm: usa a CORREÇÃO quando ela é um NCM; "OK" confirma o da coluna
    classif_fiscal_ncm. SOBRESCREVE (é dado verificado pela contabilidade).
  - fabricante: sigla canonizada (mesma tabela do import do mestre).
    DIVER = genérico → não mexe no fabricante.
Formato NCM: 8 dígitos sem pontos (como a contabilidade/Siscomex usam).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import produto  # noqa: E402

CANON = {
    "RAYBE": "Raybestos", "SONNA": "Sonnax", "ALLOM": "Allomatic",
    "TRICO": "Tricomponent", "PSMFG": "PS Bearings", "ALTO": "Alto",
    "DIVER": None,  # genérico: preserva o que estiver no cadastro
}
_NCM = re.compile(r"^\d{8}$")


def main() -> None:
    linhas = json.loads(
        (Path(__file__).resolve().parents[1] / "data" / "correcao_trabalho.json")
        .read_text(encoding="utf-8")
    )
    alterados = ncm_mudou = fab_mudou = 0
    problemas: list[str] = []
    for l in linhas:
        ncm = l["correcao"] if l["correcao"].upper() != "OK" else l["ncm_antigo"]
        ncm = ncm.strip()
        if not _NCM.match(ncm):
            problemas.append(f"{l['codigo']}: NCM inválido {ncm!r}")
            continue
        p = produto.obter(l["codigo"])
        if p is None:
            problemas.append(f"{l['codigo']}: não está no cadastro")
            continue
        campos: dict = {}
        if p.ncm != ncm:
            campos["ncm"] = ncm
            ncm_mudou += 1
        fab = CANON.get(l["marca"])
        if fab is not None and p.fabricante != fab:
            campos["fabricante"] = fab
            fab_mudou += 1
        if campos:
            produto.atualizar_campos(l["codigo"], campos)
            alterados += 1
    print(f"linhas: {len(linhas)} | produtos alterados: {alterados} | "
          f"ncm mudou: {ncm_mudou} | fabricante mudou: {fab_mudou}")
    for pr in problemas:
        print("PROBLEMA:", pr)


if __name__ == "__main__":
    main()
