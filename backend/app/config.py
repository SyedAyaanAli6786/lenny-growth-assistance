from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://lenny:lenny@localhost:5432/lenny"

    # Provider toggle
    llm_provider: Literal["anthropic", "ollama"] = "ollama"

    # Anthropic / Claude Agent SDK
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # Retrieval
    retrieval_top_k: int = 5
    retrieval_min_score: float = 0.5

    # Ops
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"
    provider_timeout_seconds: float = 60.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
