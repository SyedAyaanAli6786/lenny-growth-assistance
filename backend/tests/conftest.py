import os
from urllib.parse import urlsplit, urlunsplit


def _test_database_url() -> str | None:
    """Point the test suite at a separate database ("<db>_test") instead of
    the one the running app actually uses. Before this, pytest ran straight
    against settings.database_url — the app's real dev database — so every
    test run left behind rows like "Test session" / "Anything?" permanently
    in the user's actual chat history. This must be resolved and exported
    *before* app.config/app.db.session are imported anywhere, since
    get_settings() is lru_cache'd and app/db/session.py builds its engine
    from settings.database_url at import time — whichever DATABASE_URL is in
    os.environ at that first import wins for the rest of the process.
    """
    from dotenv import dotenv_values

    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    base_url = os.environ.get("DATABASE_URL") or dotenv_values(env_path).get("DATABASE_URL")
    if not base_url:
        return None
    parts = urlsplit(base_url)
    db_name = parts.path.lstrip("/")
    if not db_name.endswith("_test"):
        db_name = f"{db_name}_test"
    return urlunsplit((parts.scheme, parts.netloc, f"/{db_name}", parts.query, parts.fragment))


_test_url = _test_database_url()
if _test_url:
    os.environ["DATABASE_URL"] = _test_url

import asyncio  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import ProgrammingError  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402


async def _ensure_database_exists(database_url: str) -> None:
    """CREATE DATABASE for the test database if it doesn't exist yet — a
    fresh Postgres instance only has the app's configured database, not its
    "_test" counterpart. Connects to Postgres's "postgres" maintenance
    database to do it, since you can't CREATE DATABASE while connected to the
    database being created.
    """
    parts = urlsplit(database_url)
    db_name = parts.path.lstrip("/")
    maintenance_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment))

    engine = create_async_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            exists = await conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": db_name})
            if exists.scalar() is None:
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    except ProgrammingError:
        pass  # created concurrently by another test process — fine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def db_available() -> bool:
    """Integration tests need a real Postgres+pgvector instance (see docker-compose's
    `db` service). Skip gracefully instead of erroring when it isn't running, so
    `pytest` from a plain checkout still exercises all the pure-function unit tests.
    """
    settings = get_settings()
    try:
        await _ensure_database_exists(settings.database_url)
        engine = create_async_engine(settings.database_url)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)
                # engine.connect() only autobegins a transaction; against the
                # real "lenny" db this was always a no-op (schema already
                # existed via Alembic, so create_all had nothing to do) which
                # masked that nothing here was ever committed. A fresh
                # "lenny_test" db has no schema yet, so this now matters.
                await conn.commit()
            return True
        finally:
            await engine.dispose()
    except Exception:
        return False


@pytest_asyncio.fixture
async def client(db_available):
    if not db_available:
        pytest.skip("Postgres with pgvector is not reachable — run `docker compose up -d db` for API tests")

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
