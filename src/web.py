"""Servidor web (FastAPI) — LBWMA.

Centro: o CADASTRO de produtos. O invoice e o "adicionar código" alimentam o
cadastro; as planilhas (DUIMP / completa) são exportadas a partir dele.

Rotas:
  GET    /                          -> a página única
  GET    /api/produtos              -> lista o cadastro (busca, filtro incompletos)
  GET    /api/produtos/{cod}        -> ficha de um produto
  PUT    /api/produtos/{cod}        -> salva edição da ficha (cria se não existir)
  POST   /api/produtos/{cod}/imagem -> upload da imagem (jpg)
  GET    /api/produtos/{cod}/imagem -> serve a imagem
  DELETE /api/produtos/{cod}/imagem -> remove a imagem
  POST   /api/processar             -> invoice (PDF) -> NDJSON streaming (upsert no cadastro)
  POST   /api/adicionar             -> busca/compoe 1 código e cadastra (regera se já existe)
  POST   /api/exportar              -> gera + salva planilha (DUIMP/completa) com nome
  GET    /api/planilhas             -> lista planilhas salvas
  GET    /api/planilhas/{id}/download -> baixa (xlsx na DUIMP; zip na completa)
  DELETE /api/planilhas/{id}        -> apaga planilha salva

Rodar:  python run.py   (ou: python -m uvicorn src.web:app --reload)
"""
from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src import configuracoes, imagens, importacao, produto as produto_mod, saida
from src.config import settings
from src.descricao import carregar_templates
from src.dominio import ItemInvoice
from src.pipeline import obter_ou_compor, processar_stream
from src.produto import to_dict

FRONT_DIR = Path(__file__).parent / "frontend"

app = FastAPI(title="LBWMA — Importação")
app.mount("/static", StaticFiles(directory=FRONT_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (FRONT_DIR / "index.html").read_text(encoding="utf-8")


# --- padrões nível-declaração (país de origem, fabric/revend) ---------------
@app.get("/api/configuracoes")
def api_get_config():
    return configuracoes.obter()


@app.put("/api/configuracoes")
async def api_set_config(request: Request):
    body = await request.json()
    return configuracoes.salvar(body.get("padroes", body))


# --- cadastro de produtos ---------------------------------------------------
@app.get("/api/produtos")
def api_listar(busca: str = Query(""), incompletos: bool = Query(False)):
    produtos = produto_mod.listar(busca=busca, so_incompletos=incompletos)
    linhas = [to_dict(p) for p in produtos]
    return {
        "linhas": linhas,
        "total": len(linhas),
        "incompletos": sum(1 for d in linhas if d["incompleto"]),
    }


@app.get("/api/produtos/{codigo}")
def api_produto(codigo: str):
    p = produto_mod.obter(codigo)
    if p is None:
        return JSONResponse({"erro": "produto não encontrado"}, status_code=404)
    return to_dict(p)


@app.put("/api/produtos/{codigo}")
async def api_salvar_produto(codigo: str, request: Request):
    body = await request.json()
    campos = body.get("campos", body)  # aceita {campos:{...}} ou o dict direto
    p = produto_mod.atualizar_campos(codigo, campos)
    return to_dict(p)


# --- imagem -----------------------------------------------------------------
@app.post("/api/produtos/{codigo}/imagem")
async def api_upload_imagem(codigo: str, file: UploadFile = File(...)):
    dados = await file.read()
    if not dados:
        return JSONResponse({"erro": "arquivo vazio"}, status_code=400)
    imagens.salvar(codigo, dados)
    p = produto_mod.atualizar_campos(codigo, {"imagem": imagens.nome_arquivo(codigo)})
    return to_dict(p)


@app.get("/api/produtos/{codigo}/imagem")
def api_get_imagem(codigo: str):
    if not imagens.tem(codigo):
        return JSONResponse({"erro": "sem imagem"}, status_code=404)
    return FileResponse(imagens.caminho(codigo), media_type="image/jpeg")


@app.delete("/api/produtos/{codigo}/imagem")
def api_del_imagem(codigo: str):
    imagens.remover(codigo)
    p = produto_mod.atualizar_campos(codigo, {"imagem": ""})
    return to_dict(p)


# --- invoice (streaming) ----------------------------------------------------
@app.post("/api/processar")
async def api_processar(
    file: UploadFile = File(...),
    ia: bool = Query(False),
    limite: int | None = Query(None),
):
    dados = await file.read()
    tmp = Path(tempfile.gettempdir()) / f"invoice_{uuid.uuid4().hex}.pdf"
    tmp.write_bytes(dados)

    def gen():
        try:
            for tipo, payload in processar_stream(tmp, limite=limite, usar_llm=ia):
                if tipo == "item":
                    payload = to_dict(payload)
                yield json.dumps({"tipo": tipo, "dado": payload}, ensure_ascii=False) + "\n"
        finally:
            tmp.unlink(missing_ok=True)

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# --- adicionar/regerar 1 código --------------------------------------------
@app.post("/api/adicionar")
async def api_adicionar(request: Request, ia: bool = Query(False)):
    """Busca no catálogo/site, compõe e cadastra UM código. Se já existe, regera a
    descrição (forcar=True). marca='raybestos' cobre o catálogo e o fallback do site."""
    body = await request.json()
    codigo = (body.get("codigo") or "").strip()
    if not codigo:
        return JSONResponse({"erro": "informe um código"}, status_code=400)
    item = ItemInvoice(codigo=codigo, qtd_shipped=0, marca="raybestos")
    p = obter_ou_compor(item, carregar_templates(), usar_llm=ia, forcar=True)
    return to_dict(p)


# --- importação de planilha (round-trip) -----------------------------------
@app.post("/api/importar")
async def api_importar(file: UploadFile = File(...)):
    dados = await file.read()
    if not dados:
        return JSONResponse({"erro": "arquivo vazio"}, status_code=400)
    try:
        resumo = importacao.importar(dados)
    except Exception as e:  # noqa: BLE001 — vira mensagem amigável pro front
        return JSONResponse({"erro": f"falha ao ler a planilha: {e}"}, status_code=400)
    if resumo.get("erro"):
        return JSONResponse(resumo, status_code=400)
    return resumo


# --- exportação + planilhas salvas -----------------------------------------
@app.post("/api/exportar")
async def api_exportar(request: Request):
    body = await request.json()
    nome = (body.get("nome") or "").strip()
    tipo = (body.get("tipo") or "duimp").strip()
    codigos = body.get("codigos") or []
    if tipo not in ("duimp", "completa"):
        return JSONResponse({"erro": "tipo deve ser 'duimp' ou 'completa'"}, status_code=400)
    if not codigos:
        return JSONResponse({"erro": "selecione ao menos um produto"}, status_code=400)
    rec = saida.salvar_planilha(nome, tipo, codigos)
    return rec


@app.get("/api/planilhas")
def api_planilhas():
    return {"linhas": saida.listar_planilhas()}


@app.get("/api/planilhas/{pid}/download")
def api_download(pid: int):
    res = saida.preparar_download(pid)
    if res is None:
        return JSONResponse({"erro": "planilha não encontrada"}, status_code=404)
    caminho, nome_arq = res
    media = (
        "application/zip"
        if nome_arq.endswith(".zip")
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return FileResponse(caminho, filename=nome_arq, media_type=media)


@app.delete("/api/planilhas/{pid}")
def api_del_planilha(pid: int):
    rec = saida.obter_planilha(pid)
    if rec is None:
        return JSONResponse({"erro": "planilha não encontrada"}, status_code=404)
    pasta = settings.planilhas_dir / str(pid)
    if pasta.is_dir():
        shutil.rmtree(pasta, ignore_errors=True)
    from src import db

    with db.conectar() as conn:
        conn.execute("DELETE FROM planilha WHERE id = ?", (pid,))
    return {"ok": True}
