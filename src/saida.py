"""Exportação das planilhas a partir do cadastro (Produto).

Dois artefatos, mesma ficha:
  - DUIMP    -> o layout do Catálogo de Produtos do Siscomex, do jeitinho de hoje
                (16 colunas, as 3 últimas de apoio: apague antes de importar).
  - completa -> a base inteira: as colunas DUIMP + os campos comerciais/logísticos +
                a coluna Imagem, e uma pasta `imagens/` montada ao lado do xlsx.

Planilha salva = uma pasta data/planilhas/{id}/ com o xlsx (+ imagens/ na completa) e
um registro na tabela `planilha` (nome, tipo, códigos, data). Dá pra rever e rebaixar.
"""
from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from src import db, imagens, produto as produto_mod
from src.config import settings
from src.produto import Produto

# (cabeçalho, campo do Produto). Campos especiais começam com "_" e são resolvidos
# em _valor(). None = coluna em branco (sem fonte limpa hoje).
COLUNAS_DUIMP: list[tuple[str, str | None]] = [
    ("CódigoFabricante", "codigo"),
    ("Cod. Interno", "cod_ss"),
    ("Cod. Catálogo de Produto Siscomex", "cod_sisc"),
    ("Peso", "peso"),
    ("código cClassTrib", "cclasstrib"),
    ("Medida", "medida"),
    ("NCM", "ncm"),
    ("Descrição", "desc_sisc"),
    ("Fabric/Revend", None),
    ("NVE - MATÉRIA PRIMA BASE", "nve_materia_prima"),
    ("NVE - PROCESSO DE FABRICAÇÃO", "nve_processo"),
    ("NVE - ACABAMENTO SUPERFICIAL", "nve_acabamento"),
    ("País de origem", "pais_origem"),
    ("Precisa revisão", "_precisa_revisao"),  # apoio
    ("Motivos", "_motivos"),                   # apoio
    ("Fonte", "fonte_url"),                     # apoio
]

COLUNAS_COMPLETA: list[tuple[str, str | None]] = [
    ("CódigoFabricante", "codigo"),
    ("Cod.SS", "cod_ss"),
    ("Cod.Sisc", "cod_sisc"),
    ("Peso", "peso"),
    ("cClassTrib", "cclasstrib"),
    ("Medida", "medida"),
    ("NCM", "ncm"),
    ("Desc.Sisc", "desc_sisc"),
    ("Fabricante", "fabricante"),
    ("NVE - Matéria-prima base", "nve_materia_prima"),
    ("NVE - Processo de fabricação", "nve_processo"),
    ("NVE - Acabamento superficial", "nve_acabamento"),
    ("País de origem", "pais_origem"),
    ("Descrição", "descricao"),
    ("Un. medida entrada", "un_medida_entrada"),
    ("Qtd. embalagem entrada", "qtd_embalagem_entrada"),
    ("Un. medida saída", "un_medida_saida"),
    ("Qtd. embalagem saída", "qtd_embalagem_saida"),
    ("Localização no estoque", "localizacao_estoque"),
    ("Aplicações / dados técnicos", "aplicacoes"),
    ("Características", "caracteristicas"),
    ("Veículos", "veiculos"),
    ("Revenda/Uso interno", "revenda_uso_interno"),
    ("Imagem", "_imagem"),
]

_LAYOUTS = {"duimp": COLUNAS_DUIMP, "completa": COLUNAS_COMPLETA}


def _valor(p: Produto, campo: str | None) -> object:
    if campo is None:
        return ""
    if campo == "_precisa_revisao":
        return "SIM" if p.motivos else ""
    if campo == "_motivos":
        return "; ".join(p.motivos)
    if campo == "_imagem":
        return imagens.nome_arquivo(p.codigo) if imagens.tem(p.codigo) else ""
    return getattr(p, campo, "") or ""


def construir_workbook(produtos: list[Produto], tipo: str):
    from openpyxl import Workbook

    colunas = _LAYOUTS.get(tipo)
    if colunas is None:
        raise ValueError(f"tipo de planilha desconhecido: {tipo!r}")

    wb = Workbook()
    ws = wb.active
    ws.title = "Catálogo" if tipo == "completa" else "DUIMP"
    ws.append([cab for cab, _ in colunas])
    for p in produtos:
        ws.append([_valor(p, campo) for _, campo in colunas])
    return wb


# --- nomes de arquivo seguros ----------------------------------------------
def _slug(nome: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "_", (nome or "").strip())
    return (s or "planilha")[:120]


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- export direto (sem persistir) -----------------------------------------
def exportar(produtos: list[Produto], tipo: str, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    construir_workbook(produtos, tipo).save(destino)
    return destino


# --- planilhas salvas -------------------------------------------------------
def _produtos_de(codigos: list[str]) -> list[Produto]:
    out: list[Produto] = []
    for c in codigos:
        p = produto_mod.obter(c)
        if p is not None:
            out.append(p)
    return out


def salvar_planilha(nome: str, tipo: str, codigos: list[str]) -> dict:
    """Gera o xlsx (+ imagens/ na completa), grava em data/planilhas/{id}/ e
    registra na tabela. Devolve o registro."""
    if tipo not in _LAYOUTS:
        raise ValueError(f"tipo inválido: {tipo!r}")
    produtos = _produtos_de(codigos)
    nome = (nome or "").strip() or f"planilha_{tipo}"
    criada_em = _agora()

    db.inicializar()
    with db.conectar() as conn:
        cur = conn.execute(
            "INSERT INTO planilha (nome, tipo, codigos, total, arquivo, criada_em) "
            "VALUES (?, ?, ?, ?, '', ?)",
            (nome, tipo, json.dumps([p.codigo for p in produtos], ensure_ascii=False),
             len(produtos), criada_em),
        )
        pid = cur.lastrowid

    pasta = settings.planilhas_dir / str(pid)
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"{_slug(nome)}.xlsx"
    exportar(produtos, tipo, arq)

    if tipo == "completa":
        dest_img = pasta / "imagens"
        copiadas = 0
        for p in produtos:
            if imagens.tem(p.codigo):
                dest_img.mkdir(parents=True, exist_ok=True)
                (dest_img / imagens.nome_arquivo(p.codigo)).write_bytes(
                    imagens.caminho(p.codigo).read_bytes()
                )
                copiadas += 1

    with db.conectar() as conn:
        conn.execute("UPDATE planilha SET arquivo = ? WHERE id = ?", (str(arq), pid))

    return obter_planilha(pid) or {}


def listar_planilhas() -> list[dict]:
    db.inicializar()
    with db.conectar() as conn:
        rows = conn.execute(
            "SELECT id, nome, tipo, total, criada_em FROM planilha ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def obter_planilha(pid: int) -> dict | None:
    db.inicializar()
    with db.conectar() as conn:
        row = conn.execute("SELECT * FROM planilha WHERE id = ?", (pid,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    try:
        d["codigos"] = json.loads(d.get("codigos") or "[]")
    except (TypeError, ValueError):
        d["codigos"] = []
    return d


def preparar_download(pid: int) -> tuple[Path, str] | None:
    """Caminho do arquivo pra baixar. DUIMP -> o xlsx. Completa -> zip com xlsx +
    pasta imagens/ (a pasta que o cliente espera ao lado da planilha)."""
    rec = obter_planilha(pid)
    if rec is None or not rec.get("arquivo"):
        return None
    arq = Path(rec["arquivo"])
    if not arq.exists():
        return None
    if rec["tipo"] != "completa":
        return arq, arq.name

    pasta = arq.parent
    zip_path = pasta / f"{_slug(rec['nome'])}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(arq, arq.name)
        img_dir = pasta / "imagens"
        if img_dir.is_dir():
            for img in sorted(img_dir.glob("*.jpg")):
                zf.write(img, f"imagens/{img.name}")
    return zip_path, zip_path.name
