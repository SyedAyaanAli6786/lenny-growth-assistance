import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.db.models import Base


@pytest_asyncio.fixture(scope="session")
async def db_available() -> bool:
    """Integration tests need a real Postgres+pgvector instance (see docker-compose's
    `db` service). Skip gracefully instead of erroring when it isn't running, so
    `pytest` from a plain checkout still exercises all the pure-function unit tests.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(db_available):
    if not db_available:
        pytest.skip("Postgres with pgvector is not reachable — run `docker compose up -d db` for API tests")

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
