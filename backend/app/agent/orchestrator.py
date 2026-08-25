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


def _citations_from_text(text: str, retrieved: list[RetrievedChunk]) -> list[dict]:
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
        if not used_tags or f"[S{i}]" in used_tags
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


def _build_retrieval_query(history: list[ChatMessage]) -> str:
    """A short follow-up like "the 1st one" or "what about that" carries no
    retrievable signal by itself — folding in the prior assistant turn (if
    any) gives the embedding something concrete to match against, since that's
    almost always what a short follow-up is actually referring to.
    """
    latest = history[-1].content
    if len(history) >= 2 and history[-2].role == "assistant":
        return f"{history[-2].content}\n\n{latest}"
    return latest


async def respond(
    db: AsyncSession,
    provider_name: str,
    history: list[ChatMessage],
    system_prompt_override: str | None = None,
) -> OrchestrationResult:
    """Deterministic retrieve-then-generate: retrieval never depends on the model
    deciding to call a tool, so grounding behavior is identical across providers.
    """
    retrieved = await retrieve(db, _build_retrieval_query(history))

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


async def respond_stream(
    db: AsyncSession,
    provider_name: str,
    history: list[ChatMessage],
    system_prompt_override: str | None = None,
) -> AsyncIterator[StreamDelta | StreamDone]:
    """Streaming counterpart to respond(): same retrieve-then-generate
    behavior and the same final OrchestrationResult shape, but the caller
    gets each text chunk as soon as the provider produces it instead of
    waiting for the whole reply. Citations/artifact detection still need the
    complete text, so those are only computed once, in the terminal
    StreamDone event.
    """
    retrieved = await retrieve(db, _build_retrieval_query(history))

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
    async for piece in provider.generate_stream(system_prompt, history):
        chunks.append(piece)
        yield StreamDelta(piece)

    full_text = "".join(chunks).strip()
    yield StreamDone(_finalize(full_text, provider_name, provider.model_name, retrieved))


async def run_ship30(db: AsyncSession, provider_name: str, topic_message: ChatMessage) -> OrchestrationResult:
    """Retrieve grounding for the topic, draft via the Ship 30 skill, validate,
    and do one automatic repair pass if the draft violates the format rules.
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
        return OrchestrationResult(
            response=ProviderResponse(text=decline_text, provider=provider_name, model="n/a (no model call made)"),
            citations=[],
            artifact=None,
            display_text=decline_text,
        )

    system_prompt = build_ship30_prompt(_format_sources(retrieved))

    provider = get_provider(provider_name)
    draft = await provider.generate(system_prompt, [topic_message])

    result = validate_ship30_draft(draft.text)
    if not result.ok:
        logger.warning("ship30_validation_failed", issues=result.issues, word_count=result.word_count)
        repair_prompt = build_repair_prompt(draft.text, result.issues)
        draft = await provider.generate(system_prompt, [ChatMessage(role="user", content=repair_prompt)])
        result = validate_ship30_draft(draft.text)
        if not result.ok:
            logger.warning("ship30_repair_still_failing", issues=result.issues, word_count=result.word_count)

    return _finalize(draft.text, provider_name, draft.model, retrieved)
