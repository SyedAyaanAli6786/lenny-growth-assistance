import math

from app.rag.retrieval import cosine_similarity, rank_chunks


def test_cosine_similarity_identical_vectors_is_one():
    v = [1.0, 2.0, 3.0]
    assert math.isclose(cosine_similarity(v, v), 1.0, rel_tol=1e-9)


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert math.isclose(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0, abs_tol=1e-9)


def test_cosine_similarity_opposite_vectors_is_negative_one():
    assert math.isclose(cosine_similarity([1.0, 0.0], [-1.0, 0.0]), -1.0, rel_tol=1e-9)


def test_cosine_similarity_zero_vector_is_defined_as_zero():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_rank_chunks_orders_by_similarity_descending():
    query = [1.0, 0.0]
    candidates = [
        ("far", [-1.0, 0.0]),
        ("close", [1.0, 0.01]),
        ("mid", [0.0, 1.0]),
    ]
    ranked = rank_chunks(query, candidates, top_k=3)
    assert [cid for cid, _ in ranked] == ["close", "mid", "far"]


def test_rank_chunks_respects_top_k():
    query = [1.0, 0.0]
    candidates = [(str(i), [1.0, i * 0.01]) for i in range(10)]
    ranked = rank_chunks(query, candidates, top_k=3)
    assert len(ranked) == 3
