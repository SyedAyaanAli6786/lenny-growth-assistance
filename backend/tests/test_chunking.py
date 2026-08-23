from app.rag.chunking import chunk_transcript


def test_empty_body_returns_no_chunks():
    assert chunk_transcript("") == []
    assert chunk_transcript("   \n\n  ") == []


def test_short_body_becomes_single_chunk():
    body = "Paragraph one.\n\nParagraph two."
    chunks = chunk_transcript(body, words_per_chunk=100, overlap_words=10)
    assert len(chunks) == 1
    assert "Paragraph one." in chunks[0].content
    assert "Paragraph two." in chunks[0].content
    assert chunks[0].index == 0


def test_long_body_splits_into_multiple_chunks_with_overlap():
    paragraphs = [" ".join(f"word{p}_{i}" for i in range(40)) for p in range(6)]
    body = "\n\n".join(paragraphs)

    chunks = chunk_transcript(body, words_per_chunk=100, overlap_words=20)

    assert len(chunks) > 1
    # indices are sequential starting at 0
    assert [c.index for c in chunks] == list(range(len(chunks)))
    # overlap: the tail of chunk N should reappear at the head of chunk N+1
    for i in range(len(chunks) - 1):
        tail_words = chunks[i].content.split()[-5:]
        assert " ".join(tail_words) in chunks[i + 1].content


def test_oversized_single_paragraph_is_windowed():
    huge_paragraph = " ".join(f"w{i}" for i in range(500))
    chunks = chunk_transcript(huge_paragraph, words_per_chunk=100, overlap_words=20)

    assert len(chunks) >= 5
    for c in chunks:
        assert len(c.content.split()) <= 100


def test_token_count_is_positive_and_roughly_proportional():
    body = " ".join(f"word{i}" for i in range(80))
    chunks = chunk_transcript(body, words_per_chunk=200, overlap_words=20)
    assert len(chunks) == 1
    assert chunks[0].token_count > 0
