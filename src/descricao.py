"""Composição da descrição DUIMP (UMA só) a partir de item + spec + template.

Padrão decodificado com o Leonardo (comparando a saída da IA com o que ele
corrige no Catálogo Siscomex):
  - UMA descrição por item (não denominação + detalhamento separados);
  - termos dele por família ("Cinta de freio", "Filtro hidráulico … com junta",
    "Kit completo (aço + fricção)"…);
  - corta nº OE, nome comercial em inglês, faixa de anos, lista longa de modelos;
  - material/junta/parafusos quando o site tem (raspado, nunca inventado);
  - frase de fechamento padrão por família.

A IA monta a descrição seguindo a 'estrutura' do template. Sem LLM, cai pro
determinístico (termo do template + texto da invoice) e marca revisão.
"""
from __future__ import annotations

import json
import re
import string
from pathlib import Path

import yaml

from src import llm
from src.config import settings
from src.dominio import DescricaoDUIMP, ItemInvoice, SpecProduto

_GENERICO = {
    "tipo": "",
    "nome": "Peça para transmissão automática (autopeça)",
    "ncm_sugerida": "",
    "denominacao": "",
    "detalhamento_instrucoes": (
        "Descreva em uma frase técnica: tipo do produto + código + 'para "
        "transmissão automática' + aplicação (transmissão/veículo). PT-BR."
    ),
}


_CACHE_DESC = settings.cache_dir / "descricoes.json"


def _ler_cache_desc() -> dict:
    return json.loads(_CACHE_DESC.read_text(encoding="utf-8")) if _CACHE_DESC.exists() else {}


def _cache_desc_set(codigo: str, desc: "DescricaoDUIMP") -> None:
    """Guarda só descrições BOAS (redigidas pela IA). Fallback degradado não entra,
    pra ser re-tentado com IA numa próxima rodada."""
    cache = _ler_cache_desc()
    cache[codigo] = {
        "descricao": desc.descricao,
        "ncm_sugerida": desc.ncm_sugerida,
        "template": desc.template,
        "fonte_url": desc.fonte_url,
        "precisa_revisao": desc.precisa_revisao,
        "motivos": desc.motivos,
    }
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    _CACHE_DESC.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def ler_cache_descricoes() -> dict:
    """Todas as descrições já redigidas/salvas (código -> registro). É a 'base'."""
    return _ler_cache_desc()


def _desc_de_cache(item: ItemInvoice, c: dict) -> DescricaoDUIMP:
    return DescricaoDUIMP(
        codigo=item.codigo,
        descricao=c.get("descricao", ""),
        ncm_sugerida=c.get("ncm_sugerida", ""),
        template=c.get("template", ""),
        fonte_url=c.get("fonte_url", ""),
        qtd_shipped=item.qtd_shipped,
        origem=item.origem,
        precisa_revisao=c.get("precisa_revisao", False),
        motivos=list(c.get("motivos", [])),
    )


def carregar_templates() -> list[dict]:
    d: Path = settings.templates_dir
    return [yaml.safe_load(f.read_text(encoding="utf-8")) for f in sorted(d.glob("*.yaml"))]


def escolher_template(item: ItemInvoice, spec: SpecProduto, templates: list[dict]) -> dict | None:
    """Casa por 'gatilhos', respeitando 'prioridade' (maior primeiro). Um gatilho
    'cod:XXX' casa por PREFIXO do código (ancorado, sem falso-positivo no texto);
    os demais casam por substring no código + descrição do invoice + specs."""
    alvo = f"{item.codigo} {item.descricao_invoice} {' '.join(spec.atributos.values())}".lower()
    codigo_up = item.codigo.upper()
    for t in sorted(templates, key=lambda x: x.get("prioridade", 0), reverse=True):
        for g in t.get("gatilhos", []):
            g = str(g)
            if g.lower().startswith("cod:"):
                if codigo_up.startswith(g[4:].upper()):
                    return t
            elif g.lower() in alvo:
                return t
    return None


_MATERIAL_DISCO = (
    "Material predominantemente composto por materiais orgânicos à base de celulose, "
    "podendo conter fibras de carbono, resinas aglutinantes e pós metálicos, conforme "
    "a necessidade da aplicação e os requisitos do fabricante."
)
# Trio de medidas "A x B x C" (diâmetro externo x interno x espessura).
_RE_TRIO = re.compile(r"\d+(?:\.\d+)?\s*[xX]\s*\d+(?:\.\d+)?\s*[xX]\s*\.?\d+(?:\.\d+)?")
def _montar_disco(item: ItemInvoice, spec: SpecProduto) -> str:
    """Descrição do disco de fricção, DETERMINÍSTICA (sem IA). Decisão do Leonardo:
    todos os itens desta família são de conversor de torque, e o site NÃO distingue
    disco revestido de composite — então sempre "Disco de fricção {código} para
    conversores de torque", + trio de medidas quando houver (de uma única fonte)."""
    trio = ""
    for fonte in (item.descricao_invoice, spec.atributos.get("aplicacao", ""), spec.atributos.get("descricao", "")):
        m = _RE_TRIO.search(fonte or "")
        if m:
            trio = re.sub(r"\s+", " ", m.group(0)).strip()
            break

    base = f"Disco de fricção {item.codigo} para conversores de torque"
    if trio:
        base += f"; {trio}"
    return f"{base}. {_MATERIAL_DISCO}"


def _montar_disco_trans(item: ItemInvoice, spec: SpecProduto) -> str:
    """Disco de fricção de embreagem de transmissão (catálogo: 'Friction Plates').
    Determinístico e simples: tipo + código + aplicação + material. Sem citar
    material comercial (high energy, kevlar…) nem dentes/medidas avulsas."""
    ap = spec.atributos.get("aplicacao", "")
    base = f"Disco de fricção {item.codigo} para transmissão automática"
    if ap:
        base += f" {ap}"
    return f"{base}. {_MATERIAL_DISCO}"


def compor(
    item: ItemInvoice,
    spec: SpecProduto,
    templates: list[dict] | None = None,
    usar_llm: bool = True,
    usar_cache: bool = True,
) -> DescricaoDUIMP:
    templates = templates if templates is not None else carregar_templates()

    # Descrição já redigida antes (por IA) -> instantâneo e estável.
    if usar_cache:
        pronto = _ler_cache_desc().get(item.codigo)
        if pronto:
            return _desc_de_cache(item, pronto)

    t = escolher_template(item, spec, templates)

    motivos: list[str] = []
    if not spec.encontrado:
        motivos.append("spec não confirmada no site do fabricante")
    elif spec.confianca != "alta":
        motivos.append("spec casada por similaridade (código não confere no site) — conferir")
    if spec.encontrado and t is None:
        motivos.append("família/NCM não definida — classificar")
    if item.confianca != "alta":
        motivos.extend(item.problemas or ["extração do invoice incerta"])

    desc = DescricaoDUIMP(
        codigo=item.codigo,
        qtd_shipped=item.qtd_shipped,
        origem=item.origem,
        template=(t or {}).get("tipo", ""),
        ncm_sugerida=(t or {}).get("ncm_sugerida", ""),
        fonte_url=spec.fonte_url,
        atributos=dict(spec.atributos),
        motivos=motivos,
        precisa_revisao=bool(motivos),
    )

    # Discos de fricção: montagem determinística (sem IA) — formato rígido demais.
    # Mesmo sem IA eles entram na base (cache), senão "Abrir base salva" nunca
    # mostraria disco — que é a maior categoria.
    tipo_t = (t or {}).get("tipo", "")
    if tipo_t in ("disco_friccao", "disco_friccao_trans"):
        desc.descricao = _montar_disco(item, spec) if tipo_t == "disco_friccao" else _montar_disco_trans(item, spec)
        if usar_cache:
            _cache_desc_set(item.codigo, desc)
        return desc

    contexto = {
        "codigo": item.codigo,
        "descricao_invoice": item.descricao_invoice,
        "origem": item.origem,
        "marca": item.marca,
        **spec.atributos,
    }
    denom_fallback = _preencher(t["denominacao"], contexto) if t and t.get("denominacao") else ""

    if usar_llm and spec.encontrado and llm.disponivel():
        try:
            saida = llm.gerar_json(_system(), _prompt(t or _GENERICO, contexto))
            texto = (saida.get("descricao") or "").strip()
            if not texto:
                raise llm.LLMIndisponivel("descricao vazia")
            desc.descricao = texto
            if usar_cache:
                _cache_desc_set(item.codigo, desc)
            return desc
        except llm.LLMIndisponivel:
            desc.motivos.append("LLM indisponível — preenchimento determinístico")
            desc.precisa_revisao = True

    # fallback determinístico (sem IA, ou IA falhou): termo do template + aplicação
    desc.descricao = denom_fallback or item.descricao_invoice
    aplic = spec.atributos.get("aplicacao", "")
    if denom_fallback and aplic and aplic not in desc.descricao:
        desc.descricao = f"{desc.descricao} {aplic}".strip()
    return desc


def _preencher(modelo: str, ctx: dict) -> str:
    campos = {nome: "" for _, nome, _, _ in string.Formatter().parse(modelo) if nome}
    try:
        return modelo.format_map({**campos, **ctx})
    except Exception:
        return modelo


def _system() -> str:
    return (
        "Você redige a descrição única (campo 'Descrição' do Catálogo de Produtos do "
        "Siscomex) de autopeças de transmissão automática. Use SOMENTE os dados "
        "fornecidos; nunca invente medida, material, código, junta ou aplicação. "
        "Responda em JSON com a chave 'descricao'."
    )


def _prompt(t: dict, ctx: dict) -> str:
    return (
        f"Família: {t.get('nome', '')}\n"
        f"Termo/estrutura da denominação: {t.get('denominacao') or '(crie uma curta em PT)'}\n"
        f"Como montar a descrição: {' '.join(t.get('detalhamento_instrucoes', '').split())}\n"
        f"Dados disponíveis (JSON): {json.dumps(ctx, ensure_ascii=False)}\n\n"
        "Gere o campo 'descricao': UMA descrição em português técnico seguindo a "
        "estrutura indicada, usando os dados. Traduza termos do inglês (mantenha "
        "consagrados: GPZ, Kolene, spline, overdrive). NÃO inclua número OE, nome "
        "comercial em inglês, nem faixa de anos (salvo se a estrutura pedir). Inclua o "
        "trecho de junta SOMENTE se houver 'junta_ref' nos dados. Se faltar um dado, "
        "omita — não invente."
    )
