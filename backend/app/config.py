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
    # top_k=3 (not 5): measured on CPU-only Ollama, a 5-chunk grounded prompt
    # to llama3.1:8b took 200s+ to generate — see provider_timeout_seconds.
    # 3 chunks materially cuts prompt-processing time and, as a side benefit,
    # dilutes the answer with less marginal context.
    retrieval_top_k: int = 3
    retrieval_min_score: float = 0.5

    # Ops
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"
    # CPU-only llama3.1:8b with a full RAG system prompt measured at 200s+ for
    # a single reply in testing (no GPU). 240s gives headroom above that
    # rather than have the mandatory local-demo path fail by default on
    # exactly the hardware it's supposed to run on. A GPU/Apple Silicon
    # machine will finish in a few seconds regardless of this ceiling.
    provider_timeout_seconds: float = 240.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
