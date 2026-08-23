from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import SourceSummary
from app.db.models import TranscriptChunk, TranscriptSource
from app.db.session import get_db

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[SourceSummary])
async def list_sources(db: AsyncSession = Depends(get_db)) -> list[SourceSummary]:
    stmt = (
        select(
            TranscriptSource.slug,
            TranscriptSource.title,
            TranscriptSource.guest,
            TranscriptSource.published_at,
            TranscriptSource.ingested_at,
            func.count(TranscriptChunk.id).label("chunk_count"),
        )
        .join(TranscriptChunk, TranscriptChunk.source_id == TranscriptSource.id, isouter=True)
        .group_by(TranscriptSource.id)
        .order_by(TranscriptSource.title)
    )
    rows = (await db.execute(stmt)).all()
    return [
        SourceSummary(
            slug=r.slug,
            title=r.title,
            guest=r.guest,
            published_at=r.published_at.isoformat() if r.published_at else None,
            chunk_count=r.chunk_count,
            ingested_at=r.ingested_at,
        )
        for r in rows
    ]
