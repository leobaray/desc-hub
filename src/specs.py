"""Busca de specs do produto por MARCA (não por invoice).

Fluxo: cache local primeiro; se não tiver, consulta o site do fabricante.
O cache (data/cache/specs.json) é o ativo mais valioso do projeto — com o tempo
acumula a ficha de cada código já visto/revisado, e não precisa raspar de novo.

Cada marca tem uma FonteSpecs própria. Sem dado confiável NÃO se inventa —
devolve encontrado=False e o item cai pra fila de revisão.

Adicionar marca = criar uma classe FonteSpecs e chamar registrar_fonte(...).
"""
from __future__ import annotations

import json
import re
from typing import Protocol, runtime_checkable

import httpx
from selectolax.parser import HTMLParser

from src.catalogo import buscar_no_catalogo
from src.config import settings
from src.dominio import ItemInvoice, SpecProduto

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@runtime_checkable
class FonteSpecs(Protocol):
    marca: str
    url_base: str

    def buscar(self, item: ItemInvoice) -> SpecProduto:
        ...


_FONTES: dict[str, FonteSpecs] = {}


def registrar_fonte(fonte: FonteSpecs) -> FonteSpecs:
    _FONTES[fonte.marca] = fonte
    return fonte


# --- cache simples em json --------------------------------------------------
def _arquivo_cache():
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    return settings.cache_dir / "specs.json"


def _ler_cache() -> dict:
    f = _arquivo_cache()
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _gravar_cache(dados: dict) -> None:
    _arquivo_cache().write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _spec_catalogo(item: ItemInvoice, rec: dict) -> SpecProduto:
    """Monta a SpecProduto a partir de um registro do catálogo. Mapeia pras MESMAS
    chaves que a fonte do site usa (aplicacao/descricao/material/junta_ref/parafusos),
    pra os templates funcionarem igual com qualquer fonte."""
    atributos = {
        "aplicacao": rec.get("aplicacao", ""),
        "descricao": rec.get("descricao", ""),
        "notes": rec.get("notes", ""),
        "categoria": rec.get("categoria", ""),
        "oe": rec.get("oe", ""),
        "thick": rec.get("thick", ""),
    }
    for k in ("material", "junta_ref", "parafusos"):
        if rec.get(k):
            atributos[k] = rec[k]
    return SpecProduto(
        codigo=item.codigo,
        marca=item.marca or "catalogo",
        encontrado=True,
        fonte_url=f"catálogo {rec.get('catalogo', '')} p.{rec.get('pagina', '')}".strip(),
        atributos={k: v for k, v in atributos.items() if v},
        confianca="alta",
    )


def buscar_specs(item: ItemInvoice, usar_cache: bool = True) -> SpecProduto:
    # 1) Catálogo local — fonte PRIMÁRIA (offline, cobre Raybestos + Allomatic).
    rec = buscar_no_catalogo(item.codigo)
    if rec is not None:
        return _spec_catalogo(item, rec)

    # 2) Cache de raspagens anteriores do site.
    chave = f"{item.marca}:{item.codigo}"
    cache = _ler_cache()
    if usar_cache and chave in cache:
        return SpecProduto(**cache[chave])

    # 3) Site do fabricante — fallback (ex.: discos de conversor, fora do catálogo).
    fonte = _FONTES.get(item.marca)
    if fonte is None:
        return SpecProduto(codigo=item.codigo, marca=item.marca, encontrado=False)
    try:
        spec = fonte.buscar(item)
    except Exception:
        # Rede caiu / site mudou / timeout: NÃO inventa — manda pra revisão.
        spec = SpecProduto(codigo=item.codigo, marca=item.marca, encontrado=False)
    if spec.encontrado:
        cache[chave] = spec.__dict__
        _gravar_cache(cache)
    return spec


# --- helpers ----------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9]+", s.upper()))


def _node_text(node) -> str:
    if node is None:
        return ""
    try:
        t = node.text(separator=" ")
    except TypeError:
        t = node.text()
    return re.sub(r"\s+", " ", t).strip()


def _slug(href: str) -> str:
    return href.rstrip("/").rsplit("/", 1)[-1]


# Tabela de specs da página de produto: rótulo do site -> chave nossa.
_LABELS_SPEC = {"Material": "material", "Gasket Type": "gasket", "Pan Bolts": "parafusos"}
# Código de junta tipo "03G925" / "22G610".
_RE_JUNTA = re.compile(r"\d{2,}[A-Z]\d{2,}")


def _extrair_specs(tree: HTMLParser) -> dict[str, str]:
    """Lê a tabela 'Material / Gasket Type / Pan Bolts' (pares rótulo+valor
    concatenados no texto do pai, ex.: 'MaterialAll Plastic')."""
    bruto: dict[str, str] = {}
    for node in tree.css("*"):
        chave = _LABELS_SPEC.get(_node_text(node))
        if not chave or chave in bruto:
            continue
        par = node.parent
        rotulo = _node_text(node)
        partxt = _node_text(par) if par is not None else ""
        if partxt.startswith(rotulo):
            valor = partxt[len(rotulo):].strip(" :")
            if valor:
                bruto[chave] = valor

    out: dict[str, str] = {}
    if bruto.get("material"):
        out["material"] = bruto["material"]
    if bruto.get("gasket"):  # só há junta quando o site lista Gasket Type
        m = _RE_JUNTA.search(bruto["gasket"])
        if m:
            out["junta_ref"] = m.group(0)
        if bruto.get("parafusos"):
            out["parafusos"] = bruto["parafusos"]
    return out


# --- fonte de referência: Raybestos Powertrain ------------------------------
# Candidato de busca: (href, titulo, aplicacao). `titulo` é o texto do link
# ("CÓDIGO | descrição"); `aplicacao` é o alt da imagem (aplicação detalhada).
Candidato = tuple[str, str, str]


class RaybestosSpecs:
    """Busca no site da Raybestos. Estratégia:

    1. /search?query={codigo} -> casa o SLUG do produto com o código (slug é o
       identificador confiável: 'rgpz-278' vs 'rgpz-278-845re' já desambigua).
    2. se o código não existe no site (comum: o invoice da Gearbox usa SKU
       próprio, ex.: FRMHYUND07), refaz a busca pela descrição/aplicação do
       invoice e desempata por sobreposição de tokens com título + aplicação.
    3. nada conclusivo / ambíguo -> encontrado=False (revisão), nunca chute.

    Confiança: 'alta' só quando casou pelo código; 'media' quando casou por
    descrição (o compositor marca esses pra conferência humana).
    """

    marca = "raybestos"
    url_base = "https://www.raybestospowertrain.com"

    def buscar(self, item: ItemInvoice) -> SpecProduto:
        cand = self._procurar(item.codigo, item)
        casou_codigo = cand is not None

        if cand is None and item.descricao_invoice:
            cand = self._procurar(item.descricao_invoice, item, exigir_codigo=False)

        if cand is None:
            return SpecProduto(
                codigo=item.codigo, marca=self.marca, encontrado=False, fonte_url=self.url_base
            )

        href, titulo, aplicacao = cand
        url = self.url_base + href if href.startswith("/") else href
        codigo_site = titulo.split("|", 1)[0].strip() or _slug(href).upper()

        descricao_site, specs = self._dados_produto(url)
        atributos = {
            "titulo": titulo,
            "codigo_site": codigo_site,
            "aplicacao": aplicacao,
            "descricao": descricao_site or aplicacao,
            **specs,
        }
        return SpecProduto(
            codigo=item.codigo,
            marca=self.marca,
            encontrado=True,
            fonte_url=url,
            atributos={k: v for k, v in atributos.items() if v},
            confianca="alta" if casou_codigo else "media",
        )

    def _get(self, url: str, params: dict | None = None) -> str:
        r = httpx.get(
            url,
            params=params,
            timeout=settings.http_timeout,
            follow_redirects=True,
            headers={"User-Agent": _UA},
        )
        r.raise_for_status()
        return r.text

    def _candidatos(self, query: str) -> list[Candidato]:
        """Lê /search e devolve os cards de produto. Cada card:
        <div class=search-result-item...> <a class=...image-link-block><img alt=...>
        <a class=...page-link...>CÓDIGO | descrição</a> ..."""
        tree = HTMLParser(self._get(f"{self.url_base}/search", params={"query": query}))
        out: list[Candidato] = []
        vistos: set[str] = set()
        for card in tree.css("div[class*='search-result-item']"):
            link = card.css_first("a[class*='search-results-page-link']")
            if link is None:  # fallback: 1o anchor com href + texto
                link = next(
                    (a for a in card.css("a") if (a.attributes.get("href") and _node_text(a))),
                    None,
                )
            href = (link.attributes.get("href") if link else "") or ""
            if not href or href in vistos:  # a página repete cards (desktop/mobile)
                continue
            vistos.add(href)
            img = card.css_first("img")
            alt = (img.attributes.get("alt") or "") if img is not None else ""
            out.append((href, _node_text(link), re.sub(r"\s+", " ", alt).strip()))
        return out

    def _procurar(
        self, query: str, item: ItemInvoice, exigir_codigo: bool = True
    ) -> Candidato | None:
        candidatos = self._candidatos(query)
        if not candidatos:
            return None

        alvo = _norm(item.codigo)
        exatos = [c for c in candidatos if _norm(_slug(c[0])) == alvo]
        if len(exatos) == 1:
            return exatos[0]
        if len(exatos) > 1:
            return self._desempatar(exatos, item, min_score=1, margem=1)

        if exigir_codigo:
            return None
        return self._desempatar(candidatos, item, min_score=3, margem=2)

    def _desempatar(
        self, candidatos: list[Candidato], item: ItemInvoice, min_score: int = 1, margem: int = 1
    ) -> Candidato | None:
        """Escolhe por sobreposição de tokens da descrição do invoice com
        título + aplicação do candidato. Só decide se o melhor tiver `min_score`
        tokens em comum E vencer o 2º colocado por `margem` — senão é ambíguo e
        devolve None (revisão). Conservador de propósito: na busca por descrição
        (código não bate no site) é fácil casar o produto errado."""
        alvo = _tokens(item.descricao_invoice)
        if not alvo:
            return candidatos[0] if len(candidatos) == 1 else None

        ranqueados = sorted(
            ((len(alvo & _tokens(f"{c[1]} {c[2]}")), c) for c in candidatos),
            key=lambda x: x[0],
            reverse=True,
        )
        melhor_score, melhor = ranqueados[0]
        segundo = ranqueados[1][0] if len(ranqueados) > 1 else 0
        if melhor_score >= min_score and (melhor_score - segundo) >= margem:
            return melhor
        return None

    def _dados_produto(self, url: str) -> tuple[str, dict[str, str]]:
        """Devolve (descrição do produto, specs da tabela: material/junta_ref/parafusos)."""
        try:
            tree = HTMLParser(self._get(url))
        except Exception:
            return "", {}
        rich = tree.css_first(".w-richtext")
        descricao = _node_text(rich)[:1500] if rich is not None else _node_text(tree.css_first("h1"))
        return descricao, _extrair_specs(tree)


class AllomaticSpecs:
    """Site da Allomatic (allomatic.com) — Webflow, mesma busca /search?query= do
    Raybestos. Diferenças: os cards NÃO trazem título/alt (o código vem só no slug
    da URL, ex.: /transmission-filters/515489), e a página de produto põe a
    aplicação no h1 e as specs na tabela (Gasket Type / Pan Bolts / Material).

    Casa SÓ por código (slug) — sem fallback por descrição (não há texto no card).
    Nada conclusivo / rede caiu -> encontrado=False (revisão), nunca chute.
    """

    marca = "allomatic"
    url_base = "https://www.allomatic.com"

    # 1º segmento da URL -> categoria (alinha com as categorias do catálogo).
    _CATEGORIAS = {
        "transmission-filters": "Filters",
        "friction-clutch-plates": "Friction Plates",
        "steel-clutch-plates": "Steel Plates",
        "bands": "Bands",
        "sprags": "Sprags",
    }

    def _get(self, url: str, params: dict | None = None) -> str:
        r = httpx.get(
            url, params=params, timeout=settings.http_timeout,
            follow_redirects=True, headers={"User-Agent": _UA},
        )
        r.raise_for_status()
        return r.text

    def _hrefs(self, query: str) -> list[str]:
        """hrefs dos cards da busca (o código está no último segmento do slug)."""
        tree = HTMLParser(self._get(f"{self.url_base}/search", params={"query": query}))
        out: list[str] = []
        vistos: set[str] = set()
        for card in tree.css("div[class*='search-result-item']"):
            link = card.css_first("a[class*='search-results-page-link']") or next(
                (a for a in card.css("a") if a.attributes.get("href")), None
            )
            href = (link.attributes.get("href") if link else "") or ""
            if href and href not in vistos:
                vistos.add(href)
                out.append(href)
        return out

    def buscar(self, item: ItemInvoice) -> SpecProduto:
        alvo = _norm(item.codigo)
        try:
            hrefs = self._hrefs(item.codigo)
        except Exception:
            return SpecProduto(codigo=item.codigo, marca=self.marca, encontrado=False, fonte_url=self.url_base)

        href = next((h for h in hrefs if _norm(_slug(h)) == alvo), None)
        if href is None:
            return SpecProduto(codigo=item.codigo, marca=self.marca, encontrado=False, fonte_url=self.url_base)

        url = self.url_base + href if href.startswith("/") else href
        categoria = self._CATEGORIAS.get(href.strip("/").split("/")[0], "")
        try:
            tree = HTMLParser(self._get(url))
        except Exception:
            return SpecProduto(codigo=item.codigo, marca=self.marca, encontrado=False, fonte_url=url)

        aplicacao = _node_text(tree.css_first("h1"))
        atributos = {
            "aplicacao": aplicacao,
            "descricao": aplicacao,
            "categoria": categoria,
            "codigo_site": _slug(href).upper(),
            **_extrair_specs(tree),
        }
        return SpecProduto(
            codigo=item.codigo,
            marca=self.marca,
            encontrado=True,
            fonte_url=url,
            atributos={k: v for k, v in atributos.items() if v},
            confianca="alta",  # casou pelo código (slug)
        )


class SonnaxSpecs:
    """Site da Sonnax (sonnax.com) — Rails. SEM catálogo: o site é a fonte.

    Pesquisar o código em /search?query= faz **302 DIRETO** pra /parts/<id>-<slug>
    quando o código existe; quando não existe, devolve **200** (página de resultados).
    Então o próprio redirect já é o match exato — não precisa parsear cards.

    A página de produto traz: nome + "Part No. <código>" no h1; as aplicações
    (transmissões) no 1º h2; e uma descrição rica e pronta na meta description
    (ex.: "Sonnax PTFE-impregnated pump bushing 104034A ... for GM 6L50, 6L80...").
    Nossos códigos SÃO os part numbers da Sonnax (o h1 mostra o mesmo código).

    Sem redirect pra /parts/ -> encontrado=False (revisão), nunca chute.
    """

    marca = "sonnax"
    url_base = "https://www.sonnax.com"

    def _get(self, url: str, params: dict | None = None, follow: bool = True):
        return httpx.get(
            url, params=params, timeout=settings.http_timeout,
            follow_redirects=follow, headers={"User-Agent": _UA},
        )

    def buscar(self, item: ItemInvoice) -> SpecProduto:
        try:
            r = self._get(f"{self.url_base}/search", params={"query": item.codigo}, follow=False)
        except Exception:
            return SpecProduto(codigo=item.codigo, marca=self.marca, encontrado=False, fonte_url=self.url_base)

        loc = r.headers.get("location", "") if 300 <= r.status_code < 400 else ""
        if "/parts/" not in loc:  # 200 = sem match exato; redirect p/ outra coisa = ignora
            return SpecProduto(codigo=item.codigo, marca=self.marca, encontrado=False, fonte_url=self.url_base)

        url = loc if loc.startswith("http") else self.url_base + loc
        try:
            tree = HTMLParser(self._get(url).text)
        except Exception:
            return SpecProduto(codigo=item.codigo, marca=self.marca, encontrado=False, fonte_url=url)

        h1 = _node_text(tree.css_first("h1"))
        nome = re.split(r"\s*Part No\.?\s*", h1, maxsplit=1)[0].strip() if h1 else ""
        md = tree.css_first("meta[name='description']")
        descricao = (md.attributes.get("content") or "").strip() if md is not None else ""
        aplicacao = _node_text(tree.css_first("h2"))

        atributos = {
            "titulo": nome,
            "categoria": nome,          # tipo do produto (ex.: "Oversized Pump Bushing")
            "aplicacao": aplicacao,     # transmissões (1º h2)
            "descricao": descricao or aplicacao,
            "codigo_site": item.codigo,
        }
        return SpecProduto(
            codigo=item.codigo,
            marca=self.marca,
            encontrado=True,
            fonte_url=url,
            atributos={k: v for k, v in atributos.items() if v},
            confianca="alta",  # o redirect da busca já é o match exato pelo código
        )


registrar_fonte(RaybestosSpecs())
registrar_fonte(AllomaticSpecs())
registrar_fonte(SonnaxSpecs())
# Próximas marcas: alto, psbearings, tricomponent.
