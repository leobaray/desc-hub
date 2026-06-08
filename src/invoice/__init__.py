"""Pacote de parsers de invoice. Importar um modulo aqui registra o parser dele."""
from src.invoice import gearbox       # noqa: F401  (registra GearboxParser)
from src.invoice import sonnax        # noqa: F401  (registra SonnaxParser)
from src.invoice import tricomponent  # noqa: F401  (registra TricomponentParser)
