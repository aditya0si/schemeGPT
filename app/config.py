from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    groq_api_key: str = ""
    database_url: str = "postgresql+psycopg2://scheme:scheme@localhost:5432/schemegpt"
    embedding_model: str = "intfloat/multilingual-e5-small"
    groq_model: str = "llama-3.3-70b-versatile"
    data_dir: str = "data/schemes"
    # Admin token required for POST /ingest via the X-Admin-Token header.
    # Leave blank to disable manual re-ingestion (startup auto-ingestion is
    # unchanged and still runs when the vector store is empty).
    admin_token: str = ""
    # Comma-separated list of browser origins allowed by CORS. The Streamlit
    # web UI talks to the API server-side (no browser CORS), so only origins
    # that open the API directly from a browser need to be listed. Defaults to
    # the local Streamlit dev origins.
    cors_origins: str = "http://localhost:8501,http://127.0.0.1:8501"

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
    )


settings = Settings()


def data_dir_path() -> Path:
    return ROOT_DIR / settings.data_dir
