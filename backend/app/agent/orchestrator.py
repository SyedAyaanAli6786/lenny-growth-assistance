import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.anthropic_provider import AnthropicProvider
from app.agent.base import ChatMessage, LLMProvider, ProviderResponse
from app.agent.ollama_provider import OllamaProvider
from app.agent.skills.ship30 import build_repair_prompt, build_ship30_prompt, validate_ship30_draft
from app.artifacts.detect import Artifact, detect_artifact, strip_artifact_fence
from app.logging import get_logger
from app.rag.retrieval import RetrievedChunk, retrieve

logger = get_logger(__name__)

_PROVIDERS: dict[str, LLMProvider] = {}


def get_provider(name: str) -> LLMProvider:
    if name not in _PROVIDERS:
        if name == "anthropic":
            _PROVIDERS[name] = AnthropicProvider()
        elif name == "ollama":
            _PROVIDERS[name] = OllamaProvider()
        else:
            raise ValueError(f"Unknown provider: {name}")
    return _PROVIDERS[name]


GROUNDED_SYSTEM_PROMPT = """You are the Lenny Growth Assistant, a product & growth expert assistant \
grounded strictly in transcripts from Lenny's Podcast and Newsletter.

Rules:
- Answer ONLY using the numbered sources below. Do not use outside knowledge about \
companies, people, or growth tactics beyond what the sources say.
- Cite sources inline using their tag, e.g. [S1], [S2], right after the claim they support.
- If the sources do not contain enough information to answer, say so explicitly \
("The transcripts I have don't cover this") instead of guessing. Do not cite a source \
you didn't actually use.
- Keep answers focused and skimmable: short paragraphs, bullets for lists.
- If asked to produce a document, essay, or HTML snippet, output it inside a fenced code \
block (```markdown or ```html) so it can be rendered as an artifact.

Sources:
{sources}
"""

NO_SOURCES_BLOCK = "(No transcript sources cleared the relevance threshold for this question.)"


def _format_sources(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return NO_SOURCES_BLOCK
    lines = []
    for i, c in enumerate(chunks, start=1):
        guest = f" — guest: {c.guest}" if c.guest else ""
        lines.append(f"[S{i}] {c.title}{guest} (relevance {c.score})\n{c.content}")
    return "\n\n".join(lines)


@dataclass(frozen=True)
class OrchestrationResult:
    response: ProviderResponse
    citations: list[dict]
    artifact: Artifact | None
    display_text: str  # what the chat bubble shows — artifact fences replaced with a pointer


@dataclass(frozen=True)
class StreamDelta:
    """One text chunk produced during respond_stream() — append to the
    in-progress chat bubble as it arrives."""

    text: str


@dataclass(frozen=True)
class StreamDone:
    """Terminal event from respond_stream(): the same OrchestrationResult
    respond() would have returned, computed once the full reply is known."""

    result: OrchestrationResult


@dataclass(frozen=True)
class StreamRestart:
    """Only emitted by run_ship30_stream(): a failed draft is about to be
    regenerated via the repair prompt. Tells the caller to clear whatever
    text it's displayed so far, rather than appending the repair pass's
    deltas after the discarded draft's."""


def _citations_from_text(text: str, retrieved: list[RetrievedChunk]) -> list[dict]:
    """Only cite sources the reply actually tagged with [S1]-style markers.

    Used to fall back to "no tags -> attribute every retrieved chunk" on the
    theory that a weak model answered correctly but forgot to tag. Reported
    live: that fallback fires just as readily when a reply has no tags
    because it *declined* — "I can't help with weather information" carries
    no [S1] tags either, and every retrieved chunk (whatever weakly matched
    the query, however irrelevant) got attached to it as if it grounded the
    decline. Free-text decline phrasing isn't reliable to pattern-match on
    either (varies by model/provider), so untagged text is now always
    citation-free — a real but untagged grounded reply under-credits its
    sources, which is a smaller trust problem than crediting sources a reply
    never used at all.
    """
    if not text.strip():
        return []
    used_tags = {f"[S{i}]" for i in range(1, len(retrieved) + 1) if f"[S{i}]" in text}
    return [
        {
            "source_id": c.source_id,
            "chunk_id": c.chunk_id,
            "title": c.title,
            "guest": c.guest,
            "url": c.url,
            "score": c.score,
        }
        for i, c in enumerate(retrieved, start=1)
        if f"[S{i}]" in used_tags
    ]


def _finalize(text: str, provider_name: str, model_name: str, retrieved: list[RetrievedChunk]) -> OrchestrationResult:
    """Shared by respond()/respond_stream(): once the full reply text is
    known (immediately for a non-streaming call, or after the last delta for
    a streaming one), citations/artifact/display_text are derived from it
    identically either way.
    """
    citations = _citations_from_text(text, retrieved)
    artifact = detect_artifact(text)
    display_text = strip_artifact_fence(text) if artifact else text
    return OrchestrationResult(
        response=ProviderResponse(text=text, provider=provider_name, model=model_name),
        citations=citations,
        artifact=artifact,
        display_text=display_text,
    )


async def _retrieve_for_history(db: AsyncSession, history: list[ChatMessage]) -> list[RetrievedChunk]:
    """Retrieve grounding for the latest message in a multi-turn conversation.

    Tries the latest message alone first. Only if that clears nothing does it
    retry with the prior assistant turn folded in — a short follow-up like
    "the 1st one" or "what about that" carries no retrievable signal by
    itself, and folding in what it's replying to gives the embedding
    something concrete to match against. Trying alone-first rather than
    unconditionally combining matters: an unrelated follow-up in an existing
    conversation (e.g. "what's the weather in Tokyo" right after a PLG
    activation discussion) has its own clear, independent meaning that
    retrieves nothing on its own — but combining it with a long, topically
    dense prior turn was pulling in that prior turn's unrelated matches
    instead, which then got misattributed as if they grounded a reply that
    used none of them.
    """
    latest = history[-1].content
    retrieved = await retrieve(db, latest)
    if retrieved or len(history) < 2 or history[-2].role != "assistant":
        return retrieved
    return await retrieve(db, f"{history[-2].content}\n\n{latest}")


async def respond(
    db: AsyncSession,
    provider_name: str,
    history: list[ChatMessage],
    system_prompt_override: str | None = None,
) -> OrchestrationResult:
    """Deterministic retrieve-then-generate: retrieval never depends on the model
    deciding to call a tool, so grounding behavior is identical across providers.
    """
    retrieved = await _retrieve_for_history(db, history)

    if not retrieved and system_prompt_override is None:
        # Deterministic decline instead of a prompt-only instruction: testing
        # against a small local model showed it will confidently answer from
        # its own parametric knowledge even when told not to (see PRD "Local
        # model quality" risk). Skipping the model call when nothing cleared
        # the relevance threshold makes "no grounding -> no fabricated
        # answer" hold regardless of how well a given model follows
        # instructions.
        logger.info("no_retrieval_short_circuit", provider=provider_name)
        decline_text = "The transcripts I have don't cover this — I don't have grounded material to answer from."
        return OrchestrationResult(
            response=ProviderResponse(text=decline_text, provider=provider_name, model="n/a (no model call made)"),
            citations=[],
            artifact=None,
            display_text=decline_text,
        )

    system_prompt = system_prompt_override or GROUNDED_SYSTEM_PROMPT.format(sources=_format_sources(retrieved))

    provider = get_provider(provider_name)
    provider_response = await provider.generate(system_prompt, history)

    return _finalize(provider_response.text, provider_name, provider_response.model, retrieved)


async def _stoppable(agen, stop_event: asyncio.Event | None):
    """Yield from agen, but interruptible by stop_event even while agen is
    still waiting on its very next item — not just between items that have
    already arrived.

    A plain "check the flag after each yield" loop can't do this: nothing
    re-checks the flag until the provider actually produces something, and
    for Ollama specifically, "still thinking, no token yet" can last many
    seconds — a stop click during that window would silently do nothing
    until (if ever) a token showed up. Races the pending anext() against the
    stop signal instead, and — critically — only ever cancels anext() when
    stop actually fires, never on a timeout/poll: cancelling a suspended
    async-generator frame closes it for good, so a generator can't be safely
    "polled and resumed" by repeatedly cancelling and retrying.
    """
    if stop_event is None:
        async for item in agen:
            yield item
        return

    stop_task = asyncio.ensure_future(stop_event.wait())
    next_task: asyncio.Task | None = None
    try:
        while True:
            next_task = asyncio.ensure_future(agen.__anext__())
            done, _pending = await asyncio.wait({next_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            if stop_task in done:
                next_task.cancel()
                try:
                    await next_task
                except (asyncio.CancelledError, StopAsyncIteration):
                    pass
                next_task = None
                break
            try:
                yield next_task.result()
            except StopAsyncIteration:
                next_task = None
                break
    finally:
        # If we get here via an exception (e.g. the *consumer* of this
        # generator was itself cancelled — Starlette cancels a
        # StreamingResponse's task when it detects the client disconnected),
        # next_task can still be in flight against `agen`. Leaving it running
        # means agen.aclose() (called by our own caller's finally, right
        # after this one) fails with "aclose(): asynchronous generator is
        # already running" — which used to abort the whole generation on any
        # real disconnect, defeating the entire point of streaming this so
        # persistence survives a dropped connection.
        if next_task is not None and not next_task.done():
            next_task.cancel()
            try:
                await next_task
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
        if not stop_task.done():
            stop_task.cancel()
            try:
                await stop_task
            except asyncio.CancelledError:
                pass


async def respond_stream(
    db: AsyncSession,
    provider_name: str,
    history: list[ChatMessage],
    system_prompt_override: str | None = None,
    stop_event: asyncio.Event | None = None,
) -> AsyncIterator[StreamDelta | StreamDone]:
    """Streaming counterpart to respond(): same retrieve-then-generate
    behavior and the same final OrchestrationResult shape, but the caller
    gets each text chunk as soon as the provider produces it instead of
    waiting for the whole reply. Citations/artifact detection still need the
    complete text, so those are only computed once, in the terminal
    StreamDone event.

    stop_event lets a user-initiated "stop generating" request end this early
    without any special-casing at the persistence layer: breaking out of the
    loop below (see _stoppable) still falls through to the same
    _finalize()/StreamDone as a natural completion, so a stopped reply is
    persisted exactly like a finished one, just shorter. This whole
    endpoint's request/task is deliberately never cancelled to achieve that —
    only the single pending "get the next token" wait inside _stoppable ever
    is, and only once stop is actually requested. Cancelling the outer
    request would mean performing the async DB persistence from inside an
    exception handler on an already-cancelled task, a real asyncio footgun
    (a second cancellation can land mid-cleanup); this design never needs to.
    """
    retrieved = await _retrieve_for_history(db, history)

    if not retrieved and system_prompt_override is None:
        logger.info("no_retrieval_short_circuit", provider=provider_name)
        decline_text = "The transcripts I have don't cover this — I don't have grounded material to answer from."
        yield StreamDelta(decline_text)
        yield StreamDone(
            OrchestrationResult(
                response=ProviderResponse(text=decline_text, provider=provider_name, model="n/a (no model call made)"),
                citations=[],
                artifact=None,
                display_text=decline_text,
            )
        )
        return

    system_prompt = system_prompt_override or GROUNDED_SYSTEM_PROMPT.format(sources=_format_sources(retrieved))
    provider = get_provider(provider_name)

    chunks: list[str] = []
    agen = provider.generate_stream(system_prompt, history)
    try:
        async for piece in _stoppable(agen, stop_event):
            chunks.append(piece)
            yield StreamDelta(piece)
    finally:
        # Always close the provider's own generator explicitly (rather than
        # relying on GC to eventually do it via reference counting) so the
        # underlying HTTP stream to Ollama/Anthropic is torn down promptly
        # whether we finished, stopped early, or an error propagated through.
        await agen.aclose()

    full_text = "".join(chunks).strip()
    yield StreamDone(_finalize(full_text, provider_name, provider.model_name, retrieved))


async def _generate_streamed(
    provider: LLMProvider,
    system_prompt: str,
    messages: list[ChatMessage],
    stop_event: asyncio.Event | None,
    collected: list[str],
) -> AsyncIterator[str]:
    """Stream one provider.generate_stream() call, appending each piece to
    `collected` as it arrives. `collected` is an out-parameter rather than a
    return value because async generators can't `return` one (a SyntaxError)
    — the caller reads the accumulated text from it once this is exhausted.
    Used twice by run_ship30_stream(): once for the initial draft, once for
    the repair pass if the draft fails validation.
    """
    agen = provider.generate_stream(system_prompt, messages)
    try:
        async for piece in _stoppable(agen, stop_event):
            collected.append(piece)
            yield piece
    finally:
        await agen.aclose()


async def run_ship30_stream(
    db: AsyncSession,
    provider_name: str,
    topic_message: ChatMessage,
    stop_event: asyncio.Event | None = None,
) -> AsyncIterator[StreamDelta | StreamRestart | StreamDone]:
    """Streaming counterpart to what used to be run_ship30(): same
    retrieve -> draft -> validate -> (repair once if needed) -> finalize
    flow, but the caller sees each text chunk as soon as the provider
    produces it, the same way respond_stream() works for regular chat.

    This isn't just consistency with the chat endpoint — it's the actual fix
    for a real bug: a full Ship 30 essay plus a possible repair pass can run
    200-400+s on this CPU-only setup, and a single non-streamed response
    sitting completely idle that long is exactly the shape of request a
    proxy, browser, or OS idle-timeout is liable to drop. Confirmed live: a
    real essay-generation request's connection was dropped by something in
    the stack well before the ~45-minute (repair pass included, under heavy
    system load) generation finished — the reply still persisted correctly
    since non-streaming requests aren't cancelled on disconnect, but the
    user's own tab had no way to know that and showed nothing. Streaming
    keeps the connection actively sending data the whole time instead.
    """
    retrieved = await retrieve(db, topic_message.content)

    if not retrieved:
        # Same rationale as the no-retrieval short-circuit in respond(): don't
        # ask the model to draft a "grounded" essay with nothing to ground it in.
        logger.info("ship30_no_retrieval_short_circuit", provider=provider_name)
        decline_text = (
            "I don't have transcript material on this topic to draft a grounded Ship 30 "
            "essay from — try a product/growth topic covered in the knowledge base."
        )
        yield StreamDelta(decline_text)
        yield StreamDone(
            OrchestrationResult(
                response=ProviderResponse(text=decline_text, provider=provider_name, model="n/a (no model call made)"),
                citations=[],
                artifact=None,
                display_text=decline_text,
            )
        )
        return

    system_prompt = build_ship30_prompt(_format_sources(retrieved))
    provider = get_provider(provider_name)

    draft_chunks: list[str] = []
    async for piece in _generate_streamed(provider, system_prompt, [topic_message], stop_event, draft_chunks):
        yield StreamDelta(piece)
    draft_text = "".join(draft_chunks).strip()
    model_name = provider.model_name

    result = validate_ship30_draft(draft_text)
    if not result.ok and not (stop_event is not None and stop_event.is_set()):
        # If stop was already requested, the draft's failing validation is
        # just a side effect of being cut short — starting a repair pass now
        # would fire an extra provider call and a spurious "restart" event
        # for a generation the user already asked to end.
        logger.warning("ship30_validation_failed", issues=result.issues, word_count=result.word_count)
        yield StreamRestart()
        repair_prompt = build_repair_prompt(draft_text, result.issues)
        repair_messages = [ChatMessage(role="user", content=repair_prompt)]
        repair_chunks: list[str] = []
        async for piece in _generate_streamed(provider, system_prompt, repair_messages, stop_event, repair_chunks):
            yield StreamDelta(piece)
        draft_text = "".join(repair_chunks).strip()
        result = validate_ship30_draft(draft_text)
        if not result.ok:
            logger.warning("ship30_repair_still_failing", issues=result.issues, word_count=result.word_count)

    yield StreamDone(_finalize(draft_text, provider_name, model_name, retrieved))
