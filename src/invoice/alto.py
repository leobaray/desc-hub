"""Parser do invoice Alto (altousa.com) — proforma de 2 colunas INTERLEAVED.

O modo texto do pymupdf embaralha as colunas (lê todos os códigos juntos, depois
todas as quantidades etc.), então aqui parseamos por COORDENADAS. No template do
Alto ("Proforma Print Form oqpp"), por posição x:

    x≈ 34  SHIPPED        x≈160  ITEM NUMBER (código)
    x≈121  B/O            x≈386  Made In (país de origem)
    x≈140  U/M            x≈474  UNIT PRICE      x≈539  AMOUNT

Uma linha de item é a que tem um CÓDIGO em x[150,250] E o SHIPPED (inteiro) em
x[15,55]. A origem é o país (alfabético) em x[375,425] dentro do intervalo y do
item. Sem origem -> confiança baixa, nunca inventa.

Bandas de x calibradas neste template; se o Alto mudar o layout, reavaliar.
"""
from __future__ import annotations

import re

from src.dominio import ItemInvoice
from src.invoice.base import registrar

_CODE = re.compile(r"^\d[\dA-Z\-]{4,}$")   # código Alto: começa com dígito, >= 5 chars
_INT = re.compile(r"^\d+$")
_PAIS = re.compile(r"^[A-Za-z][A-Za-z/]{2,}$")  # país (USA, MEXICO, USA/JAPAN...)


class AltoParser:
    nome = "alto"

    def detectar(self, texto: str) -> bool:
        return "alto products corp" in texto.lower()

    def extrair(self, paginas: list[str], pdf=None) -> list[ItemInvoice]:
        if pdf is None:
            return []  # precisa do PDF pras coordenadas
        import fitz

        itens: list[ItemInvoice] = []
        doc = fitz.open(str(pdf))
        try:
            for n in range(len(doc)):
                words = doc[n].get_text("words")  # (x0,y0,x1,y1, palavra, ...)

                # agrupa em linhas visuais (y) e acha as linhas que são item
                linhas: dict[int, list] = {}
                for w in words:
                    linhas.setdefault(round(w[1] / 4) * 4, []).append(w)

                itens_y: list[tuple[int, str, int]] = []
                for yk in sorted(linhas):
                    ws = linhas[yk]
                    cod = next((w[4] for w in ws if 150 <= w[0] <= 250 and _CODE.match(w[4])), None)
                    shp = next((w[4] for w in ws if 15 <= w[0] <= 55 and _INT.match(w[4])), None)
                    if cod and shp:
                        itens_y.append((yk, cod, int(shp)))

                for idx, (yk, cod, shp) in enumerate(itens_y):
                    y_fim = itens_y[idx + 1][0] if idx + 1 < len(itens_y) else yk + 30
                    origem = next(
                        (w[4] for w in words
                         if 375 <= w[0] <= 425 and yk - 2 <= w[1] < y_fim
                         and _PAIS.match(w[4]) and w[4].lower() not in ("made", "currency")),
                        "",
                    )
                    item = ItemInvoice(
                        codigo=cod, qtd_shipped=shp, origem=origem,
                        marca="alto", pagina=n + 1,
                    )
                    if not origem:
                        item.problemas = ["origem (Made In) não encontrada"]
                        item.confianca = "baixa"
                    itens.append(item)
        finally:
            doc.close()
        return itens


registrar(AltoParser())
