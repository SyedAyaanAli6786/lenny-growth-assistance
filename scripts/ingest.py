"""Idempotent ingestion CLI for the transcripts under data/transcripts/.

Run from the backend container/venv (needs the `app` package importable):
    python -m scripts.ingest [--path data/transcripts]

Re-running is safe: a file whose content hash hasn't changed is skipped;
a changed file has its old chunks replaced (see TranscriptSource.content_hash).
"""

import argparse
import asyncio
import hashlib
import re
from datetime import date
from pathlib import Path

import frontmatter
from sqlalchemy import delete, select

from app.db.models import TranscriptChunk, TranscriptSource
from app.db.session import async_session_factory
from app.logging import configure_logging, get_logger
from app.rag.chunking import chunk_transcript
from app.rag.embeddings import embed_text

configure_logging("INFO")
logger = get_logger("ingest")


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "untitled"


def _content_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


async def ingest_file(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)
    content_hash = _content_hash(raw)

    title = post.get("title") or path.stem
    guest = post.get("guest")
    url = post.get("url") or post.get("youtube_url")
    published_at = _parse_date(post.get("date") or post.get("published_at"))
    slug = _slugify(path.stem)

    async with async_session_factory() as db:
        existing = (await db.execute(select(TranscriptSource).where(TranscriptSource.slug == slug))).scalar_one_or_none()

        if existing and existing.content_hash == content_hash:
            logger.info("skip_unchanged", slug=slug)
            return

        if existing:
            await db.execute(delete(TranscriptChunk).where(TranscriptChunk.source_id == existing.id))
            existing.title = title
            existing.guest = guest
            existing.url = url
            existing.published_at = published_at
            existing.content_hash = content_hash
            source = existing
        else:
            source = TranscriptSource(
                slug=slug, title=title, guest=guest, url=url, published_at=published_at, content_hash=content_hash
            )
            db.add(source)

        await db.flush()

        chunks = chunk_transcript(post.content)
        logger.info("chunking", slug=slug, chunk_count=len(chunks))

        for chunk in chunks:
            embedding = await embed_text(chunk.content)
            db.add(
                TranscriptChunk(
                    source_id=source.id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding=embedding,
                )
            )

        await db.commit()
        logger.info("ingested", slug=slug, chunk_count=len(chunks))


async def main(transcripts_dir: Path) -> None:
    files = sorted(p for p in transcripts_dir.glob("*.md") if p.stem.lower() != "readme")
    if not files:
        logger.warning("no_transcript_files_found", path=str(transcripts_dir))
        return

    logger.info("ingest_start", file_count=len(files))
    for path in files:
        try:
            await ingest_file(path)
        except Exception as exc:  # keep going: one bad file shouldn't kill the whole run
            logger.error("ingest_file_failed", file=str(path), error=str(exc))
    logger.info("ingest_complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="data/transcripts")
    args = parser.parse_args()
    asyncio.run(main(Path(args.path)))
