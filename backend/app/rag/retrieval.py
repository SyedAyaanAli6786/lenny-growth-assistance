from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import TranscriptChunk, TranscriptSource
from app.rag.embeddings import embed_text


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    source_id: str
    title: str
    guest: str | None
    url: str | None
    content: str
    score: float  # cosine similarity, higher is better


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure function used both by the pgvector-backed path (as a sanity check)
    and directly by unit tests, without needing a database."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rank_chunks(query_embedding: list[float], candidates: list[tuple[str, list[float]]], top_k: int) -> list[tuple[str, float]]:
    """Pure ranking function: given a query vector and (id, embedding) pairs,
    return the top_k ids with their similarity score, descending."""
    scored = [(cid, cosine_similarity(query_embedding, emb)) for cid, emb in candidates]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]


async def retrieve(db: AsyncSession, query: str, top_k: int | None = None, min_score: float | None = None) -> list[RetrievedChunk]:
    settings = get_settings()
    top_k = top_k or settings.retrieval_top_k
    min_score = min_score if min_score is not None else settings.retrieval_min_score

    query_embedding = await embed_text(query)

    stmt = (
        select(
            TranscriptChunk.id,
            TranscriptChunk.content,
            TranscriptChunk.source_id,
            TranscriptSource.title,
            TranscriptSource.guest,
            TranscriptSource.url,
            TranscriptChunk.embedding.cosine_distance(query_embedding).label("distance"),
        )
        .join(TranscriptSource, TranscriptChunk.source_id == TranscriptSource.id)
        .order_by("distance")
        .limit(top_k)
    )
    result = await db.execute(stmt)
    rows = result.all()

    retrieved = []
    for row in rows:
        similarity = 1 - row.distance  # pgvector cosine_distance = 1 - cosine_similarity
        if similarity < min_score:
            continue
        retrieved.append(
            RetrievedChunk(
                chunk_id=str(row.id),
                source_id=str(row.source_id),
                title=row.title,
                guest=row.guest,
                url=row.url,
                content=row.content,
                score=round(similarity, 4),
            )
        )
    return retrieved
