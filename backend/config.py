from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://raguser:ragpassword@localhost:5432/ragdb"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    groq_api_key: str = ""
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()