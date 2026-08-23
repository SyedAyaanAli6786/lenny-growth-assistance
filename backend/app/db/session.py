from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

# NullPool: asyncpg connections are bound to the event loop that opened them,
# and a pooled connection reused on a different loop raises "attached to a
# different loop". A single Uvicorn process only ever has one loop, so this
# doesn't cost real pooling in production — but it's what makes the test
# suite (which pytest-asyncio runs across per-test event loops) work against
# this module-level engine without cross-loop connection reuse errors.
engine = create_async_engine(settings.database_url, poolclass=NullPool)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def check_db_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
