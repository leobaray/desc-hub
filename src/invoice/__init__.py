"""Pacote de parsers de invoice. Importar um módulo aqui registra o parser dele.

Cada fornecedor novo: criar `src/invoice/<nome>.py` e importá-lo abaixo.
"""
from src.invoice import gearbox       # noqa: F401  (registra GearboxParser)
from src.invoice import sonnax        # noqa: F401  (registra SonnaxParser)
from src.invoice import tricomponent  # noqa: F401  (registra TricomponentParser)
from src.invoice import psbearings    # noqa: F401  (registra PsBearingsParser)
from src.invoice import alto          # noqa: F401  (registra AltoParser)
