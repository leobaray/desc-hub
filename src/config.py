from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM — Ollama Cloud (mesma conta do projeto roger). Usado SÓ pra COMPOR a
    # descrição; nunca pra extrair dado do invoice. Com `ollama_api_key` vazio,
    # cai pro Ollama LOCAL em `ollama_base_url`.
    ollama_api_key: str = ""
    ollama_base_url: str = "https://ollama.com"
    ollama_model: str = "qwen3.5:397b-cloud"
    llm_timeout: int = 180  # por chamada; o retry paciente cuida de soluço transitório
    http_timeout: int = 30  # requisições aos sites dos fabricantes

    templates_dir: Path = Path("./data/templates")
    cache_dir: Path = Path("./data/cache")
    saida_dir: Path = Path("./data/saida")

    # Centro do sistema: o cadastro de produtos vive aqui (SQLite, 1 arquivo).
    db_path: Path = Path("./data/app.db")
    # Store de imagens (uma por código): data/imagens/{codigo}.jpg.
    imagens_dir: Path = Path("./data/imagens")
    # Planilhas exportadas e salvas (cada uma na sua pasta: xlsx + imagens/).
    planilhas_dir: Path = Path("./data/planilhas")

    host: str = "0.0.0.0"
    port: int = 8000


settings = Settings()
