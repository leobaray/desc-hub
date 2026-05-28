"""O Produto — o novo centro do sistema.

Antes a "base" era um cache de descrições (descricoes.json, keyed por código). Agora
o centro é o CADASTRO: cada código é uma ficha rica (~23 campos) que alimenta duas
planilhas — a DUIMP (subset) e a completa (tudo + imagem).

Origem dos campos (decidido com o Leonardo):
  - o sistema preenche: desc_sisc (pipeline), ncm (sugerida), fabricante, pais_origem
    (ORIGIN do invoice), cclasstrib (fixo "1"), seed de aplicações (do catálogo);
  - só humano/importação: peso, medida, cod_ss, cod_sisc, NVE×3, embalagem, estoque,
    descrição comercial, características, revenda/uso interno, imagem.

Regra-mãe (DNA herdado): o que não dá pra confirmar NÃO é inventado. Aqui isso vira
COMPLETUDE: falta campo obrigatório -> registro "incompleto" (laranja na UI). É o
mesmo `precisa_revisao` de antes, ampliado da descrição pra ficha inteira.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime

from src import db
from src.catalogo import buscar_no_catalogo
from src.dominio import DescricaoDUIMP, ItemInvoice, SpecProduto


@dataclass
class Produto:
    codigo: str
    fabricante: str = ""
    # --- bloco DUIMP ---
    cod_ss: str = ""
    cod_sisc: str = ""
    peso: str = ""
    cclasstrib: str = "1"
    medida: str = ""
    ncm: str = ""
    desc_sisc: str = ""
    nve_materia_prima: str = ""
    nve_processo: str = ""
    nve_acabamento: str = ""
    pais_origem: str = ""
    # --- bloco extra (planilha completa) ---
    descricao: str = ""
    un_medida_entrada: str = ""
    qtd_embalagem_entrada: str = ""
    un_medida_saida: str = ""
    qtd_embalagem_saida: str = ""
    localizacao_estoque: str = ""
    aplicacoes: str = ""
    veiculos: str = ""
    caracteristicas: str = ""
    revenda_uso_interno: str = ""
    imagem: str = ""
    # --- metadados ---
    template: str = ""
    ncm_sugerida: str = ""
    fonte_url: str = ""
    motivos: list[str] = field(default_factory=list)
    criado_em: str = ""
    atualizado_em: str = ""


# Campos que precisam estar preenchidos pro registro ficar "verde" (completo).
# Ficam de fora: `codigo` (é a chave), `cclasstrib` (default "1"), `caracteristicas`
# (você marcou como opcional) e os metadados.
CAMPOS_OBRIGATORIOS = [
    "fabricante", "cod_ss", "cod_sisc", "peso", "medida", "ncm", "desc_sisc",
    "nve_materia_prima", "nve_processo", "nve_acabamento", "pais_origem",
    "descricao", "un_medida_entrada", "qtd_embalagem_entrada", "un_medida_saida",
    "qtd_embalagem_saida", "localizacao_estoque", "aplicacoes", "veiculos",
    "revenda_uso_interno", "imagem",
]

# Campos que SÓ o humano/importação preenche — o pipeline nunca sobrescreve.
_CAMPOS_MANUAIS = {
    "peso", "medida", "cod_ss", "cod_sisc", "nve_materia_prima", "nve_processo",
    "nve_acabamento", "un_medida_entrada", "qtd_embalagem_entrada",
    "un_medida_saida", "qtd_embalagem_saida", "localizacao_estoque", "descricao",
    "caracteristicas", "revenda_uso_interno", "imagem",
}

_NOMES_CAMPOS = {f.name for f in fields(Produto)}


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- completude (a regra do "laranja") -------------------------------------
def campos_faltando(p: Produto) -> list[str]:
    return [c for c in CAMPOS_OBRIGATORIOS if not str(getattr(p, c, "") or "").strip()]


def incompleto(p: Produto) -> bool:
    return bool(campos_faltando(p))


def to_dict(p: Produto) -> dict:
    """Ficha + status de completude, no formato que a UI consome."""
    d = asdict(p)
    falta = campos_faltando(p)
    d["faltando"] = falta
    d["incompleto"] = bool(falta)
    d["tem_imagem"] = bool((p.imagem or "").strip())
    return d


# --- serialização SQLite <-> Produto ---------------------------------------
def _to_row(p: Produto) -> dict:
    d = asdict(p)
    d["motivos"] = json.dumps(p.motivos, ensure_ascii=False)
    return d


def _from_row(row) -> Produto:
    d = {k: row[k] for k in row.keys() if k in _NOMES_CAMPOS}
    bruto = d.get("motivos")
    try:
        d["motivos"] = json.loads(bruto) if bruto else []
    except (TypeError, ValueError):
        d["motivos"] = []
    for k, v in d.items():
        if v is None and k != "motivos":
            d[k] = ""
    return Produto(**d)


# --- repositório ------------------------------------------------------------
def obter(codigo: str) -> Produto | None:
    db.inicializar()
    with db.conectar() as conn:
        row = conn.execute("SELECT * FROM produto WHERE codigo = ?", (codigo,)).fetchone()
    return _from_row(row) if row else None


def existe(codigo: str) -> bool:
    db.inicializar()
    with db.conectar() as conn:
        r = conn.execute("SELECT 1 FROM produto WHERE codigo = ?", (codigo,)).fetchone()
    return r is not None


def listar(busca: str = "", so_incompletos: bool = False) -> list[Produto]:
    """Catálogo inteiro (ou filtrado). Ordena por código. A completude é calculada
    em Python (não em SQL) pra a regra do laranja ficar num lugar só."""
    db.inicializar()
    sql = "SELECT * FROM produto"
    params: list = []
    if busca:
        like = f"%{busca.strip().lower()}%"
        sql += (
            " WHERE lower(codigo) LIKE ? OR lower(desc_sisc) LIKE ?"
            " OR lower(descricao) LIKE ? OR lower(aplicacoes) LIKE ?"
        )
        params = [like, like, like, like]
    sql += " ORDER BY codigo"
    with db.conectar() as conn:
        rows = conn.execute(sql, params).fetchall()
    produtos = [_from_row(r) for r in rows]
    if so_incompletos:
        produtos = [p for p in produtos if incompleto(p)]
    return produtos


def salvar(p: Produto) -> Produto:
    """Upsert da ficha inteira (usado pela edição manual). Mantém criado_em."""
    db.inicializar()
    cols = db.colunas_produto()
    if not p.criado_em:
        p.criado_em = _agora()
    p.atualizado_em = _agora()
    row = _to_row(p)
    placeholders = ", ".join("?" for _ in cols)
    update = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in ("codigo", "criado_em"))
    with db.conectar() as conn:
        conn.execute(
            f"INSERT INTO produto ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(codigo) DO UPDATE SET {update}",
            [row[c] for c in cols],
        )
    return p


def atualizar_campos(codigo: str, campos: dict) -> Produto:
    """Edição parcial vinda da ficha. Ignora chaves desconhecidas e `codigo`."""
    p = obter(codigo) or Produto(codigo=codigo)
    for k, v in campos.items():
        if k in _NOMES_CAMPOS and k not in ("codigo", "criado_em", "atualizado_em", "motivos"):
            setattr(p, k, "" if v is None else str(v))
    return salvar(p)


def upsert_de_descricao(item: ItemInvoice, spec: SpecProduto, desc: DescricaoDUIMP) -> Produto:
    """Merge da saída do pipeline no cadastro, PRESERVANDO os campos manuais.

    System-owned (sempre atualiza): desc_sisc, template, ncm_sugerida, fonte_url, motivos.
    Seed-if-empty (semi-manual): ncm, fabricante, pais_origem, aplicacoes.
    Manuais: nunca toca (peso, medida, NVE, embalagem, estoque, descrição, imagem...).
    """
    p = obter(item.codigo) or Produto(codigo=item.codigo)

    p.desc_sisc = desc.descricao
    p.template = desc.template
    p.ncm_sugerida = desc.ncm_sugerida
    p.fonte_url = desc.fonte_url
    p.motivos = list(desc.motivos)

    if not p.ncm:
        p.ncm = desc.ncm_sugerida
    if not p.fabricante:
        p.fabricante = item.marca or spec.marca
    if not p.pais_origem:
        p.pais_origem = item.origem
    if not p.aplicacoes:
        p.aplicacoes = spec.atributos.get("aplicacao", "") or spec.atributos.get("titulo", "")

    return salvar(p)


# --- migração one-shot: descricoes.json -> tabela produto -------------------
def migrar_de_json(verbose: bool = True) -> dict:
    """Carrega o cache antigo (descricoes.json) pro cadastro e faz seed de
    aplicações do catálogo. Idempotente: não toca em código que já existe (protege
    edição manual)."""
    from src.descricao import ler_cache_descricoes

    db.inicializar()
    cache = ler_cache_descricoes()
    novos = 0
    pulados = 0
    for codigo, c in cache.items():
        if existe(codigo):
            pulados += 1
            continue
        rec = buscar_no_catalogo(codigo) or {}
        p = Produto(
            codigo=codigo,
            fabricante="raybestos",
            ncm=c.get("ncm_sugerida", ""),
            desc_sisc=c.get("descricao", ""),
            aplicacoes=rec.get("aplicacao", ""),
            template=c.get("template", ""),
            ncm_sugerida=c.get("ncm_sugerida", ""),
            fonte_url=c.get("fonte_url", ""),
            motivos=list(c.get("motivos", [])),
        )
        salvar(p)
        novos += 1
    resumo = {"novos": novos, "pulados": pulados, "total_cache": len(cache)}
    if verbose:
        print(f"[migração] {resumo}")
    return resumo


if __name__ == "__main__":
    migrar_de_json()
