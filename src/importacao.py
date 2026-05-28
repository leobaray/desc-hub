"""Importador de planilha -> cadastro (Produto).

O caminho do "mistura": você exporta a planilha completa (já pré-preenchida com o
que o sistema sabe), preenche os campos manuais no Excel e reimporta aqui. Cada
linha faz upsert no cadastro PELO CÓDIGO: preenche o que veio, preserva o resto
(célula vazia não apaga dado já cadastrado).

Tolerante a cabeçalho: normaliza o nome da coluna (sem acento, sem pontuação,
minúsculo) e casa com o campo do Produto por uma tabela de apelidos. Use o layout
da exportação completa; a coluna "Imagem" é ignorada (imagem entra por upload, não
pela célula).

    python -m src.importacao caminho/da/planilha.xlsx
"""
from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path

from src import produto as produto_mod
from src.saida import COLUNAS_COMPLETA


def _norm(s: object) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


# cabeçalho normalizado -> campo do Produto. Base: o layout da exportação completa.
_MAPA: dict[str, str] = {}
for _cab, _campo in COLUNAS_COMPLETA:
    if _campo and not _campo.startswith("_"):
        _MAPA[_norm(_cab)] = _campo

# Apelidos extras (variações de nome que sua planilha pode ter).
_APELIDOS = {
    "codigo": "codigo", "codprod": "codigo", "codigodoproduto": "codigo",
    "codinterno": "cod_ss", "codigointerno": "cod_ss",
    "codcatalogodeprodutosiscomex": "cod_sisc", "codigosiscomex": "cod_sisc",
    "codsiscomex": "cod_sisc",
    "codigocclasstrib": "cclasstrib", "classtrib": "cclasstrib",
    "pais": "pais_origem", "paisorigem": "pais_origem",
    "nvemateriaprima": "nve_materia_prima",
    "nveprocesso": "nve_processo", "nveprocessofabricacao": "nve_processo",
    "nveacabamento": "nve_acabamento",
    "quantiadaembalagemnaentrada": "qtd_embalagem_entrada",
    "quantiadaembalagemnasaida": "qtd_embalagem_saida",
    "unidadedemedidadaembalagemnasaida": "un_medida_saida",
    "unmedidaentrada": "un_medida_entrada",
    "localizacaonoestoque": "localizacao_estoque", "localizacao": "localizacao_estoque",
    "aplicacoesinformacoesdosdadostecnicos": "aplicacoes", "aplicacao": "aplicacoes",
    "revenda": "revenda_uso_interno", "usointerno": "revenda_uso_interno",
    "revendausointerno": "revenda_uso_interno",
    "descricaogeral": "descricao", "descricaocomercial": "descricao",
}
_MAPA.update(_APELIDOS)

# nunca importar pela célula (vêm de upload/sistema)
_IGNORAR = {"imagem"}


def _mapear_cabecalhos(cabecalhos: list) -> dict[int, str]:
    """índice da coluna -> campo do Produto (só as que reconhecemos)."""
    out: dict[int, str] = {}
    for i, cab in enumerate(cabecalhos):
        campo = _MAPA.get(_norm(cab))
        if campo and campo not in _IGNORAR:
            out[i] = campo
    return out


def importar(origem: str | Path | bytes) -> dict:
    """Lê o xlsx e faz upsert linha a linha. Devolve um resumo."""
    from openpyxl import load_workbook

    fonte = io.BytesIO(origem) if isinstance(origem, bytes) else origem
    wb = load_workbook(fonte, read_only=True, data_only=True)
    ws = wb.active

    linhas = list(ws.iter_rows(values_only=True))
    if not linhas:
        return {"erro": "planilha vazia", "criados": 0, "atualizados": 0, "linhas": 0}

    col2campo = _mapear_cabecalhos(list(linhas[0]))
    if "codigo" not in col2campo.values():
        return {
            "erro": "não achei a coluna do código (ex.: CódigoFabricante)",
            "reconhecidas": sorted(set(col2campo.values())),
            "criados": 0, "atualizados": 0, "linhas": 0,
        }

    criados = atualizados = ignoradas = 0
    campos_vistos: set[str] = set()
    for raw in linhas[1:]:
        valores = {
            col2campo[i]: ("" if v is None else str(v).strip())
            for i, v in enumerate(raw)
            if i in col2campo
        }
        codigo = (valores.pop("codigo", "") or "").strip()
        if not codigo:
            ignoradas += 1
            continue
        # só campos preenchidos: célula vazia preserva o que já existe no cadastro
        campos = {k: v for k, v in valores.items() if v != ""}
        existia = produto_mod.existe(codigo)
        produto_mod.atualizar_campos(codigo, campos)
        campos_vistos.update(campos.keys())
        if existia:
            atualizados += 1
        else:
            criados += 1

    return {
        "criados": criados,
        "atualizados": atualizados,
        "ignoradas_sem_codigo": ignoradas,
        "linhas": len(linhas) - 1,
        "campos_preenchidos": sorted(campos_vistos),
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("uso: python -m src.importacao caminho/da/planilha.xlsx")
        raise SystemExit(2)
    print(importar(sys.argv[1]))
