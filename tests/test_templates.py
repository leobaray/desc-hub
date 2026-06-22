"""Roteamento dos templates de família (data/templates/*.yaml).

Casos sintéticos cobrindo um representante por família — se um gatilho novo
roubar item de outra família ou uma prioridade mudar o roteamento, quebra aqui.
NCMs vêm da aba CORREÇÃO da contabilidade (2026-06).

Roda sem dependências externas: `python tests/test_templates.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.descricao import carregar_templates, escolher_template  # noqa: E402
from src.dominio import ItemInvoice, SpecProduto  # noqa: E402

CASOS = [
    ("RCPTK-001", "Torqkit complete set", "kit_completo"),
    ("RCP96-100", "GPZ Friction Module", "friction_clutch_pack"),
    ("515877", "Filter with gasket", "filtro"),
    ("R445100T", "TCW torque ring", "disco_friccao"),
    ("512568", "Friction Plates", "disco_friccao_trans"),
    ("STMFORD01", "Steel Module", "jogo_discos_aco"),
    ("513001", "Transmission band", "transmission_band"),
    ("PS97-1500", "one-way sprag", "sprag_roda_livre"),
    ("F-225740-TL", "Reamer tool kit", "kit_ferramentas"),
    ("51100", "steel plate", "disco_aco"),
    ("MI-3", "", "tampa_bocal"),
    ("104740-01K", "Pressure Regulator Valve Kit w/ spring", "valvula"),
    ("6T40-ZIP", "ZIP kit 6T40", "kit_reparo_orings"),
    ("RTX10001", "thrust needle bearing", "rolamento_axial_agulha"),
    ("332001", "ball bearing", "rolamento_radial"),
    ("GM-R-9", "bearing kit, needle bearing", "kit_rolamento"),
    ("TX-RIV-1", "rivet", "rebite"),
    ("GM-SPR-1", "return spring", "mola"),
    ("GM-ROL-1", "roller", "rolete_rolamento"),
    ("XX-1", "o-ring sealing ring", "anel_vedacao"),
]


def test_templates():
    templates = carregar_templates()

    tipos = [t["tipo"] for t in templates]
    assert len(tipos) == len(set(tipos)), "tipo duplicado"

    for t in templates:
        ncm = t["ncm_sugerida"]
        assert ncm.isdigit() and len(ncm) == 8, f"{t['tipo']}: NCM {ncm!r} fora do padrão"

    # 87089300 foi extinto pela contabilidade (rev. 2026-06-15) — não pode voltar.
    assert "87089300" not in {t["ncm_sugerida"] for t in templates}

    # NCMs remanejados na revisão de 2026-06-15.
    por_tipo = {t["tipo"]: t["ncm_sugerida"] for t in templates}
    assert por_tipo["jogo_discos_aco"] == "87084090"
    assert por_tipo["disco_aco"] == "87084090"
    assert por_tipo["kit_completo"] == "68138910"

    spec = SpecProduto(codigo="", marca="", encontrado=False)
    for codigo, desc, esperado in CASOS:
        item = ItemInvoice(codigo=codigo, descricao_invoice=desc, qtd_shipped=1, origem="US")
        t = escolher_template(item, spec, templates)
        got = (t or {}).get("tipo")
        assert got == esperado, f"{codigo}: roteou pra {got}, esperava {esperado}"

    print(f"ok — {len(templates)} templates, {len(CASOS)} casos de roteamento")


if __name__ == "__main__":
    test_templates()
