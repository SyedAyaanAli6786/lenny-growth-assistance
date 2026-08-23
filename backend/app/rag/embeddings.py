import httpx

from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)


class EmbeddingError(RuntimeError):
    """Raised when the local embedding backend is unreachable or errors."""


async def embed_text(text: str) -> list[float]:
    settings = get_settings()
    url = f"{settings.ollama_base_url}/api/embeddings"
    payload = {"model": settings.ollama_embed_model, "prompt": text}

    try:
        async with httpx.AsyncClient(timeout=settings.provider_timeout_seconds) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("embedding_request_failed", error=str(exc))
        raise EmbeddingError(f"Ollama embedding request failed: {exc}") from exc

    data = response.json()
    embedding = data.get("embedding")
    if not embedding:
        raise EmbeddingError("Ollama embedding response missing 'embedding' field")
    return embedding


async def embed_batch(texts: list[str]) -> list[list[float]]:
    return [await embed_text(t) for t in texts]
