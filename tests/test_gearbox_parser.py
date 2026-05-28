"""Smoke test do parser de referência — usa o formato REAL que o pymupdf gera
pra INVOICE RAYBESTOS (cada célula da tabela numa linha separada).

Valida o que mais importa na extração determinística:
  - pega a quantidade SHIPPED (não a ordered) em itens com back-order;
  - pega ORIGIN (não "Made in") — inclusive quando diferem (USA vs TAIWAN).

Roda sem dependências externas: `python tests/test_gearbox_parser.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.invoice.gearbox import GearboxParser  # noqa: E402

# Sequência vertical como o pymupdf extrai (ver gearbox.py).
AMOSTRA = "\n".join([
    "Ordered", "Shipped", "Back Ordered", "Item / Customer", "Number",
    # item 1
    "8", "8", "0", "FRMHYUND07", "95.03", "760.24",
    "HYUNDAI A6LF2 2WD (3 UD BRAKE) 2010-ON",
    "HTS CODE: 8708.99 93 00", "ORIGIN: USA", "Made in: USA",
    "Item Description: HYUNDAI A6LF2 2WD (3 UD BRAKE) ", "2010-ON", "Line Vol (Cu In): 0",
    # item 2 (parcial: ordered 5, shipped 3, back 2)
    "5", "3", "2", "RGPZ-278", "187.76", "563.28",
    "ZF 8HP45/845RE 11-UP",
    "HTS CODE: ", "ORIGIN: USA", "Made in: USA",
    "Item Description: ZF 8HP45/845RE 11-UP", "Line Vol (Cu In): 0",
    # item 3 (ORIGIN USA, Made in TAIWAN)
    "10", "10", "0", "513704", "28.54", "285.40",
    "59701 AW 50/40/42/42LE 89-UP",
    "HTS CODE: 8708.99", "ORIGIN: USA", "Made in: TAIWAN",
    "Item Description: 59701 AW 50/40/42/42LE 89-UP", "Line Vol (Cu In): 0",
])


def test_extrai_shipped_e_origem():
    itens = GearboxParser().extrair([AMOSTRA])
    por_codigo = {i.codigo: i for i in itens}

    assert set(por_codigo) == {"FRMHYUND07", "RGPZ-278", "513704"}, por_codigo.keys()

    # quantidade SHIPPED, não ordered (RGPZ-278: ordered 5, shipped 3)
    assert por_codigo["FRMHYUND07"].qtd_shipped == 8
    assert por_codigo["RGPZ-278"].qtd_shipped == 3
    assert por_codigo["RGPZ-278"].qtd_backordered == 2

    # ORIGIN, não "Made in" (513704: ORIGIN USA, Made in TAIWAN)
    assert por_codigo["513704"].origem == "USA"
    assert por_codigo["FRMHYUND07"].descricao_invoice.startswith("HYUNDAI A6LF2")


if __name__ == "__main__":
    test_extrai_shipped_e_origem()
    print("OK — parser extrai shipped + origem corretamente")
