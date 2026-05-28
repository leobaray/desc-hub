"""Exporta no layout do Catálogo de Produtos do Siscomex (igual ao Pasta1.xlsx).

Preenchemos o que o sistema sabe: CódigoFabricante, cClassTrib (fixo = 1), NCM,
Descrição (a descrição única) e País de origem. O resto (Cod. Interno, Catálogo
Siscomex, Peso, Medida, Fabric/Revend, NVE) fica em branco pra você completar.
As 3 últimas colunas (revisão/motivos/fonte) são APOIO — apague antes de importar.
"""
from __future__ import annotations

from pathlib import Path

from src.config import settings
from src.dominio import DescricaoDUIMP

COLUNAS = [
    "CódigoFabricante",
    "Cod. Interno",
    "Cod. Catálogo de Produto Siscomex",
    "Peso",
    "código cClassTrib",
    "Medida",
    "NCM",
    "Descrição",
    "Fabric/Revend",
    "NVE - MATÉRIA PRIMA BASE",
    "NVE - PROCESSO DE FABRICAÇÃO",
    "NVE - ACABAMENTO SUPERFICIAL",
    "País de origem",
    "Precisa revisão",  # apoio
    "Motivos",          # apoio
    "Fonte",            # apoio
]


def exportar_xlsx(descricoes: list[DescricaoDUIMP], nome: str = "descricoes_duimp.xlsx") -> Path:
    from openpyxl import Workbook

    settings.saida_dir.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Catálogo"
    ws.append(COLUNAS)
    for d in descricoes:
        ws.append([
            d.codigo, "", "", "",
            1, "", d.ncm_sugerida, d.descricao, "",
            "", "", "",
            d.origem,
            "SIM" if d.precisa_revisao else "", "; ".join(d.motivos), d.fonte_url,
        ])

    destino = settings.saida_dir / nome
    wb.save(destino)
    return destino
