from fastapi import APIRouter

from app.agent.orchestrator import get_provider
from app.api.schemas import ComponentHealth, HealthResponse
from app.config import get_settings
from app.db.session import check_db_connection

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()

    db_ok = await check_db_connection()
    db_health = ComponentHealth(status="ok" if db_ok else "down", detail=None if db_ok else "cannot connect to Postgres")

    ollama_ok = await get_provider("ollama").is_available()
    ollama_health = ComponentHealth(
        status="ok" if ollama_ok else "down",
        detail=None if ollama_ok else f"cannot reach Ollama at {settings.ollama_base_url}",
    )

    key_present = bool(settings.anthropic_api_key)
    anthropic_health = ComponentHealth(
        status="ok" if key_present else "degraded",
        detail=None if key_present else "ANTHROPIC_API_KEY not set — cloud provider disabled",
    )

    if not db_ok:
        overall = "down"  # Postgres is a hard dependency; nothing works without it.
    elif not ollama_ok or not key_present:
        overall = "degraded"  # at least one provider still works
    else:
        overall = "ok"

    return HealthResponse(status=overall, db=db_health, ollama=ollama_health, anthropic=anthropic_health)
