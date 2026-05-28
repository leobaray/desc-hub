"""Teste de integração (rede) com o site da Raybestos.

Valida os dois caminhos que importam:
  - código que EXISTE no site (RCPTK-4800) -> confiança 'alta';
  - código com variantes (RGPZ-278 -> ZF 8HP45 vs 845RE) desambiguado pela
    descrição do invoice.

Roda direto: `python tests/test_raybestos_lookup.py`
Pula sozinho se o site estiver inacessível (rede bloqueada no ambiente).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from src.dominio import ItemInvoice  # noqa: E402
from src.specs import RaybestosSpecs  # noqa: E402


def _online() -> bool:
    try:
        httpx.get("https://www.raybestospowertrain.com", timeout=5)
        return True
    except Exception:
        return False


def test_codigo_exato():
    item = ItemInvoice(
        codigo="RCPTK-4800",
        qtd_shipped=2,
        descricao_invoice="TORQKIT COMPLETE SET CHRYSLER 48RE , 2003-UP",
    )
    spec = RaybestosSpecs().buscar(item)
    assert spec.encontrado, "RCPTK-4800 deveria existir no site"
    assert spec.confianca == "alta", f"esperava confiança alta, veio {spec.confianca}"
    assert "rcptk-4800" in spec.fonte_url.lower(), spec.fonte_url
    return spec


def test_desambigua_por_descricao():
    item = ItemInvoice(
        codigo="RGPZ-278", qtd_shipped=1, descricao_invoice="ZF 8HP45/845RE 11-UP"
    )
    spec = RaybestosSpecs().buscar(item)
    assert spec.encontrado, "RGPZ-278 deveria existir no site"
    # deve escolher a variante ZF 8HP45 (rgpz-278), não a 845RE
    assert spec.fonte_url.rstrip("/").lower().endswith("rgpz-278"), spec.fonte_url
    return spec


if __name__ == "__main__":
    if not _online():
        print("SKIP — site Raybestos inacessível neste ambiente")
        raise SystemExit(0)
    for fn in (test_codigo_exato, test_desambigua_por_descricao):
        spec = fn()
        print(f"OK {fn.__name__}: {spec.atributos.get('titulo', '')} -> {spec.fonte_url}")
