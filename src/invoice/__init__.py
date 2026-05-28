"""Pacote de parsers de invoice. Importar um módulo aqui registra o parser dele.

Cada fornecedor novo: criar `src/invoice/<nome>.py` e importá-lo abaixo.
"""
from src.invoice import gearbox  # noqa: F401  (efeito colateral: registra GearboxParser)
