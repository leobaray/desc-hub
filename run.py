"""Sobe o servidor web do app de importação.

    python run.py
"""
from __future__ import annotations

import uvicorn

from src.config import settings

if __name__ == "__main__":
    uvicorn.run("src.web:app", host=settings.host, port=settings.port, reload=False)
