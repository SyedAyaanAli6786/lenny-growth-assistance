"""Pure functions for turning transcript bodies into overlapping chunks.

Kept free of I/O and DB dependencies so it's directly unit-testable.
"""

from dataclasses import dataclass

WORDS_PER_CHUNK = 450  # ~600 tokens at ~0.75 tokens/word
OVERLAP_WORDS = 60


@dataclass(frozen=True)
class Chunk:
    index: int
    content: str
    token_count: int


def _estimate_tokens(text: str) -> int:
    return max(1, round(len(text.split()) / 0.75))


def _split_long_words(words: list[str], words_per_chunk: int, overlap_words: int) -> list[list[str]]:
    """Break a single word list (e.g. one giant paragraph) into overlapping windows."""
    windows: list[list[str]] = []
    start = 0
    step = max(1, words_per_chunk - overlap_words)
    while start < len(words):
        windows.append(words[start : start + words_per_chunk])
        if start + words_per_chunk >= len(words):
            break
        start += step
    return windows


def chunk_transcript(body: str, words_per_chunk: int = WORDS_PER_CHUNK, overlap_words: int = OVERLAP_WORDS) -> list[Chunk]:
    """Split on paragraph boundaries first, then pack paragraphs into
    word-budgeted, overlapping chunks so a chunk rarely cuts a sentence.
    """
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    pending: list[list[str]] = []  # list of word-lists, flushed together into one chunk
    pending_len = 0
    chunks: list[Chunk] = []

    def flush(overlap_tail: list[str] | None = None) -> list[str]:
        """Emit the pending chunk and return the word tail to carry forward as overlap."""
        nonlocal pending, pending_len
        if pending_len == 0:
            return overlap_tail or []
        words = [w for group in pending for w in group]
        text = " ".join(words)
        chunks.append(Chunk(index=len(chunks), content=text, token_count=_estimate_tokens(text)))
        tail = words[-overlap_words:] if overlap_words else []
        pending = []
        pending_len = 0
        return tail

    for paragraph in paragraphs:
        paragraph_words = paragraph.split()

        if len(paragraph_words) > words_per_chunk:
            # Oversized paragraph: flush what we have, then window the paragraph itself.
            flush()
            for window in _split_long_words(paragraph_words, words_per_chunk, overlap_words):
                chunks.append(
                    Chunk(index=len(chunks), content=" ".join(window), token_count=_estimate_tokens(" ".join(window)))
                )
            continue

        if pending_len + len(paragraph_words) > words_per_chunk and pending_len > 0:
            tail = flush()
            if tail:
                pending.append(tail)
                pending_len += len(tail)

        pending.append(paragraph_words)
        pending_len += len(paragraph_words)

    flush()
    return chunks
