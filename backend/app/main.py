from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.base import ProviderTimeoutError, ProviderUnavailableError
from app.api import health, sessions, sources
from app.config import get_settings
from app.logging import configure_logging, get_logger
from app.rag.embeddings import EmbeddingError

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", provider=settings.llm_provider, database=settings.database_url.split("@")[-1])
    yield
    logger.info("shutdown")


app = FastAPI(title="Lenny Growth Assistant API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_response(status_code: int, code: str, message: str, component: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message, "component": component}})


@app.exception_handler(ProviderUnavailableError)
async def provider_unavailable_handler(request: Request, exc: ProviderUnavailableError) -> JSONResponse:
    logger.error("provider_unavailable", path=str(request.url), error=str(exc))
    return _error_response(503, "provider_unavailable", str(exc), component="provider")


@app.exception_handler(ProviderTimeoutError)
async def provider_timeout_handler(request: Request, exc: ProviderTimeoutError) -> JSONResponse:
    logger.error("provider_timeout", path=str(request.url), error=str(exc))
    return _error_response(504, "provider_timeout", str(exc), component="provider")


@app.exception_handler(EmbeddingError)
async def embedding_error_handler(request: Request, exc: EmbeddingError) -> JSONResponse:
    logger.error("embedding_error", path=str(request.url), error=str(exc))
    return _error_response(503, "embedding_unavailable", str(exc), component="retrieval")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", path=str(request.url), error=str(exc), exc_info=True)
    return _error_response(500, "internal_error", "An unexpected error occurred", component=None)


app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(sources.router)
