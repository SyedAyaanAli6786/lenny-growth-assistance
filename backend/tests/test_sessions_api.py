import asyncio
import json

import pytest

from app.agent.base import ChatMessage, ProviderResponse
from app.rag.retrieval import RetrievedChunk

FAKE_CHUNK = RetrievedChunk(
    chunk_id="chunk-1",
    source_id="source-1",
    title="Example Episode",
    guest="Example Guest",
    url="https://example.com/ep1",
    content="Some grounded transcript content.",
    score=0.9,
)


class FakeProvider:
    """Stands in for AnthropicProvider/OllamaProvider so API tests don't need a
    real model call — the orchestration/persistence/HTTP contract is what's
    under test here, not model quality."""

    def __init__(self, name: str, reply: str = "A grounded answer.", available: bool = True):
        self.name = name
        self.model_name = "fake-model"
        self._reply = reply
        self._available = available

    async def is_available(self) -> bool:
        return self._available

    async def generate(self, system_prompt: str, messages: list[ChatMessage]) -> ProviderResponse:
        return ProviderResponse(text=self._reply, provider=self.name, model=self.model_name)

    async def generate_stream(self, system_prompt: str, messages: list[ChatMessage]):
        # Split on spaces (not chars) so a test asserting on the accumulated
        # text still sees exactly self._reply back, just delivered in pieces.
        words = self._reply.split(" ")
        for i, word in enumerate(words):
            yield word if i == len(words) - 1 else f"{word} "


@pytest.fixture(autouse=True)
def patch_providers(monkeypatch):
    fakes = {"anthropic": FakeProvider("anthropic"), "ollama": FakeProvider("ollama")}

    def fake_get_provider(name: str):
        return fakes[name]

    monkeypatch.setattr("app.agent.orchestrator.get_provider", fake_get_provider)
    monkeypatch.setattr("app.api.sessions.get_provider", fake_get_provider)

    # Retrieval always embeds the query first (see orchestrator.respond); stub
    # that out too so these API/contract tests don't require a live Ollama.
    async def fake_embed_text(text: str) -> list[float]:
        return [0.0] * 768

    monkeypatch.setattr("app.rag.retrieval.embed_text", fake_embed_text)

    # The test DB has no ingested transcripts, so real retrieve() would always
    # return []  and trip the no-retrieval short-circuit in orchestrator.py —
    # stub in one grounded chunk so provider-path tests actually exercise the
    # provider call. test_send_message_with_no_grounding_has_empty_citations
    # overrides this back to [] to test the short-circuit itself.
    async def fake_retrieve(db, query, top_k=None, min_score=None):
        return [FAKE_CHUNK]

    monkeypatch.setattr("app.agent.orchestrator.retrieve", fake_retrieve)
    return fakes


async def test_create_and_fetch_session(client):
    resp = await client.post("/api/sessions", json={"title": "Test session"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Test session"
    assert body["llm_provider"] in ("anthropic", "ollama")

    detail = await client.get(f"/api/sessions/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["messages"] == []


async def test_list_sessions_returns_created_session(client):
    created = await client.post("/api/sessions", json={"title": "Listed session"})
    session_id = created.json()["id"]

    listing = await client.get("/api/sessions")
    assert listing.status_code == 200
    assert any(s["id"] == session_id for s in listing.json())


async def test_get_unknown_session_returns_structured_404(client):
    resp = await client.get("/api/sessions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "session_not_found"


async def test_send_message_persists_turn_and_returns_reply(client, patch_providers):
    session = (await client.post("/api/sessions", json={})).json()

    resp = await client.post(f"/api/sessions/{session['id']}/messages", json={"content": "What is activation?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"] == "A grounded answer."

    detail = await client.get(f"/api/sessions/{session['id']}")
    roles = [m["role"] for m in detail.json()["messages"]]
    assert roles == ["user", "assistant"]


async def _read_ndjson(response) -> list[dict]:
    events = []
    async for line in response.aiter_lines():
        if line:
            events.append(json.loads(line))
    return events


async def test_send_message_stream_emits_deltas_then_done(client, patch_providers):
    patch_providers["ollama"]._reply = "A grounded streamed answer."
    session = (await client.post("/api/sessions", json={})).json()

    async with client.stream(
        "POST", f"/api/sessions/{session['id']}/messages/stream", json={"content": "What is activation?"}
    ) as resp:
        assert resp.status_code == 200
        events = await _read_ndjson(resp)

    deltas = [e for e in events if e["type"] == "delta"]
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert "".join(d["text"] for d in deltas) == "A grounded streamed answer."
    assert done[0]["turn"]["message"]["content"] == "A grounded streamed answer."
    assert done[0]["turn"]["message"]["role"] == "assistant"
    assert len(done[0]["turn"]["message"]["citations"]) >= 1

    # The streamed turn must be persisted exactly like the non-streaming endpoint.
    detail = await client.get(f"/api/sessions/{session['id']}")
    roles = [m["role"] for m in detail.json()["messages"]]
    assert roles == ["user", "assistant"]


async def test_send_message_stream_persists_user_message_even_if_generation_fails(client, patch_providers):
    # Generation on a slow, CPU-only Ollama can run 30-120+s — long enough that
    # a client disconnect (or, as simulated here, a mid-stream provider crash)
    # is a real risk, not a corner case. The user's own message and the
    # session title must survive that even though no reply ever lands.
    async def failing_stream(system_prompt, messages):
        yield "Partial "
        raise RuntimeError("simulated mid-stream failure")

    patch_providers["ollama"].generate_stream = failing_stream
    session = (await client.post("/api/sessions", json={})).json()

    async with client.stream(
        "POST", f"/api/sessions/{session['id']}/messages/stream", json={"content": "What is activation?"}
    ) as resp:
        events = await _read_ndjson(resp)

    assert any(e["type"] == "error" for e in events)
    assert not any(e["type"] == "done" for e in events)

    detail = (await client.get(f"/api/sessions/{session['id']}")).json()
    assert detail["title"] == "What is activation?"
    assert [m["role"] for m in detail["messages"]] == ["user"]


async def test_stop_endpoint_ends_stream_early_and_persists_the_partial_reply(client, patch_providers):
    # A "stop generating" click should behave exactly like a natural
    # completion, just shorter — persisted the same way, no special error
    # path — rather than an abrupt cancellation. The provider here pauses
    # indefinitely right after its first chunk (simulating Ollama still
    # "thinking" with no token produced yet) so this test can verify the
    # harder case: stop must interrupt that wait itself, not just a check
    # between already-arrived chunks — a real bug in an earlier version of
    # this feature, reported live as "the stop button doesn't do anything
    # while it still says 'is thinking...'". If stop only took effect between
    # yields, "world " below would still be produced after resume_after_stop
    # is set; the fix means it must never appear.
    reached_first_chunk = asyncio.Event()
    resume_after_stop = asyncio.Event()

    async def controlled_stream(system_prompt, messages):
        yield "Hello "
        reached_first_chunk.set()
        await resume_after_stop.wait()
        yield "world "
        yield "text that must never be produced"

    patch_providers["ollama"].generate_stream = controlled_stream
    session = (await client.post("/api/sessions", json={})).json()

    async def run_stream():
        events = []
        async with client.stream(
            "POST", f"/api/sessions/{session['id']}/messages/stream", json={"content": "hi"}
        ) as resp:
            async for line in resp.aiter_lines():
                if line:
                    events.append(json.loads(line))
        return events

    task = asyncio.create_task(run_stream())
    await asyncio.wait_for(reached_first_chunk.wait(), timeout=5)

    stop_resp = await client.post(f"/api/sessions/{session['id']}/messages/stop")
    assert stop_resp.status_code == 204

    events = await asyncio.wait_for(task, timeout=5)
    resume_after_stop.set()  # only to unblock controlled_stream's own cleanup, if it's even still running

    deltas = "".join(e["text"] for e in events if e["type"] == "delta")
    assert deltas == "Hello "
    assert "world" not in deltas
    assert "must never be produced" not in deltas

    done = next(e for e in events if e["type"] == "done")
    assert done["turn"]["message"]["content"] == "Hello"

    # Persisted exactly like a normal completion — survives a fresh fetch.
    detail = (await client.get(f"/api/sessions/{session['id']}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][-1]["content"] == "Hello"


async def test_stop_before_any_token_persists_an_empty_reply_with_no_citations(client, patch_providers):
    # Reported live: clicking stop while still on "Ollama is thinking..." (no
    # token produced yet at all) must interrupt that wait too, not just a
    # pause between already-arrived tokens (see the test above). Also
    # exercises a real edge case that surfaced only once that worked: an
    # empty reply must not carry citations for sources it never actually
    # used — _citations_from_text's "model didn't use [S1] tags" fallback
    # would otherwise attach every retrieved chunk to a blank message.
    never_yields = asyncio.Event()

    async def stalls_forever(system_prompt, messages):
        await never_yields.wait()
        yield "unreachable"  # pragma: no cover

    patch_providers["ollama"].generate_stream = stalls_forever
    session = (await client.post("/api/sessions", json={})).json()

    async def run_stream():
        events = []
        async with client.stream(
            "POST", f"/api/sessions/{session['id']}/messages/stream", json={"content": "hi"}
        ) as resp:
            async for line in resp.aiter_lines():
                if line:
                    events.append(json.loads(line))
        return events

    task = asyncio.create_task(run_stream())
    await asyncio.sleep(0.1)  # let the request reach the stalled provider call

    stop_resp = await client.post(f"/api/sessions/{session['id']}/messages/stop")
    assert stop_resp.status_code == 204

    events = await asyncio.wait_for(task, timeout=5)

    assert not any(e["type"] == "delta" for e in events)
    done = next(e for e in events if e["type"] == "done")
    assert done["turn"]["message"]["content"] == ""
    assert done["turn"]["message"]["citations"] == []

    detail = (await client.get(f"/api/sessions/{session['id']}")).json()
    assert detail["messages"][-1]["content"] == ""
    assert detail["messages"][-1]["citations"] == []


async def test_stop_endpoint_is_a_no_op_when_nothing_is_generating(client):
    session = (await client.post("/api/sessions", json={})).json()
    resp = await client.post(f"/api/sessions/{session['id']}/messages/stop")
    assert resp.status_code == 204


async def test_send_message_stream_with_no_grounding_reports_decline_and_no_error(client, monkeypatch):
    async def empty_retrieve(db, query, top_k=None, min_score=None):
        return []

    monkeypatch.setattr("app.agent.orchestrator.retrieve", empty_retrieve)

    session = (await client.post("/api/sessions", json={})).json()
    async with client.stream(
        "POST", f"/api/sessions/{session['id']}/messages/stream", json={"content": "Anything?"}
    ) as resp:
        events = await _read_ndjson(resp)

    assert not any(e["type"] == "error" for e in events)
    done = next(e for e in events if e["type"] == "done")
    assert done["turn"]["message"]["citations"] == []
    assert "don't cover this" in done["turn"]["message"]["content"]


async def test_send_message_with_no_grounding_short_circuits_without_calling_provider(client, monkeypatch):
    # When nothing clears the relevance threshold, respond() should decline
    # deterministically rather than ask the model to answer ungrounded (see
    # orchestrator.py's no_retrieval_short_circuit — added after testing showed
    # a small local model will confidently hallucinate instead of declining).
    async def empty_retrieve(db, query, top_k=None, min_score=None):
        return []

    monkeypatch.setattr("app.agent.orchestrator.retrieve", empty_retrieve)

    session = (await client.post("/api/sessions", json={})).json()
    resp = await client.post(f"/api/sessions/{session['id']}/messages", json={"content": "Anything?"})
    body = resp.json()
    assert body["message"]["citations"] == []
    assert "don't cover this" in body["message"]["content"]


async def test_message_produces_artifact_when_reply_has_fenced_block(client, patch_providers):
    patch_providers["ollama"]._reply = "Here:\n\n```markdown\n# A Doc\n\nContent.\n```"
    session = (await client.post("/api/sessions", json={"title": "s"})).json()
    await client.patch(f"/api/sessions/{session['id']}/provider", json={"provider": "ollama"})

    resp = await client.post(f"/api/sessions/{session['id']}/messages", json={"content": "write a doc"})
    body = resp.json()
    assert body["artifact"] is not None
    assert body["artifact"]["type"] == "markdown"
    assert body["artifact"]["title"] == "A Doc"
    # The artifact is also embedded on the message itself, not just the
    # top-level turn response — that's what lets a past turn's artifact be
    # reopened later (see the next test).
    assert body["message"]["artifact"] is not None
    assert body["message"]["artifact"]["title"] == "A Doc"


async def test_artifact_survives_a_fresh_fetch_after_the_turn_response_is_gone(client, patch_providers):
    # Regression test: closing the artifact panel (or reloading, or switching
    # sessions and back) used to lose the artifact forever, since MessageOut
    # never carried it and GET /api/sessions/{id} had no way to recover it.
    patch_providers["ollama"]._reply = "Here:\n\n```markdown\n# A Doc\n\nContent.\n```"
    session = (await client.post("/api/sessions", json={})).json()
    await client.post(f"/api/sessions/{session['id']}/messages", json={"content": "write a doc"})

    detail = (await client.get(f"/api/sessions/{session['id']}")).json()
    assistant_message = next(m for m in detail["messages"] if m["role"] == "assistant")
    assert assistant_message["artifact"] is not None
    assert assistant_message["artifact"]["title"] == "A Doc"

    # A message with no artifact stays None, not a missing key or an error.
    user_message = next(m for m in detail["messages"] if m["role"] == "user")
    assert user_message["artifact"] is None


async def test_first_message_names_an_untitled_session(client, patch_providers):
    session = (await client.post("/api/sessions", json={})).json()
    assert session["title"] is None

    await client.post(f"/api/sessions/{session['id']}/messages", json={"content": "How should I think about activation?"})
    detail = (await client.get(f"/api/sessions/{session['id']}")).json()
    assert detail["title"] == "How should I think about activation?"

    # A second message must not overwrite the name that's already there.
    await client.post(f"/api/sessions/{session['id']}/messages", json={"content": "And retention?"})
    detail_after = (await client.get(f"/api/sessions/{session['id']}")).json()
    assert detail_after["title"] == "How should I think about activation?"


async def test_delete_session_removes_it_and_its_messages(client, patch_providers):
    session = (await client.post("/api/sessions", json={})).json()
    await client.post(f"/api/sessions/{session['id']}/messages", json={"content": "What is activation?"})

    resp = await client.delete(f"/api/sessions/{session['id']}")
    assert resp.status_code == 204

    assert (await client.get(f"/api/sessions/{session['id']}")).status_code == 404
    listing = await client.get("/api/sessions")
    assert not any(s["id"] == session["id"] for s in listing.json())


async def test_delete_unknown_session_returns_structured_404(client):
    resp = await client.delete("/api/sessions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "session_not_found"


async def test_provider_switch_updates_session(client):
    session = (await client.post("/api/sessions", json={})).json()
    resp = await client.patch(f"/api/sessions/{session['id']}/provider", json={"provider": "anthropic"})
    assert resp.status_code == 200
    assert resp.json()["llm_provider"] == "anthropic"


async def test_provider_switch_rejects_unavailable_provider(client, patch_providers):
    patch_providers["anthropic"]._available = False
    session = (await client.post("/api/sessions", json={})).json()

    resp = await client.patch(f"/api/sessions/{session['id']}/provider", json={"provider": "anthropic"})
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"]["code"] == "provider_unavailable"


async def test_ship30_endpoint_returns_markdown_artifact(client, patch_providers):
    essay = "```markdown\n# Ship 30 Essay\n\n**Bold point.**\n\nTakeaway: start by doing it.\n```"
    patch_providers["ollama"]._reply = essay

    session = (await client.post("/api/sessions", json={})).json()
    resp = await client.post(f"/api/sessions/{session['id']}/ship30", json={"content": "activation"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["artifact"]["type"] == "markdown"
    assert body["artifact"]["title"] == "Ship 30 Essay"
