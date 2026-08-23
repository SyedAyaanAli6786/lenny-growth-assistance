from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.anthropic_provider import AnthropicProvider
from app.agent.base import ChatMessage, LLMProvider, ProviderResponse
from app.agent.ollama_provider import OllamaProvider
from app.agent.skills.ship30 import build_repair_prompt, build_ship30_prompt, validate_ship30_draft
from app.artifacts.detect import Artifact, detect_artifact
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


async def respond(
    db: AsyncSession,
    provider_name: str,
    history: list[ChatMessage],
    system_prompt_override: str | None = None,
) -> OrchestrationResult:
    """Deterministic retrieve-then-generate: retrieval never depends on the model
    deciding to call a tool, so grounding behavior is identical across providers.
    """
    latest_user_message = history[-1].content
    retrieved = await retrieve(db, latest_user_message)

    if not retrieved and system_prompt_override is None:
        # Deterministic decline instead of a prompt-only instruction: testing
        # against a small local model showed it will confidently answer from
        # its own parametric knowledge even when told not to (see PRD "Local
        # model quality" risk). Skipping the model call when nothing cleared
        # the relevance threshold makes "no grounding -> no fabricated
        # answer" hold regardless of how well a given model follows
        # instructions.
        logger.info("no_retrieval_short_circuit", provider=provider_name)
        return OrchestrationResult(
            response=ProviderResponse(
                text="The transcripts I have don't cover this — I don't have grounded material to answer from.",
                provider=provider_name,
                model="n/a (no model call made)",
            ),
            citations=[],
            artifact=None,
        )

    system_prompt = system_prompt_override or GROUNDED_SYSTEM_PROMPT.format(sources=_format_sources(retrieved))

    provider = get_provider(provider_name)
    provider_response = await provider.generate(system_prompt, history)

    used_tags = {f"[S{i}]" for i in range(1, len(retrieved) + 1) if f"[S{i}]" in provider_response.text}
    citations = [
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

    artifact = detect_artifact(provider_response.text)

    return OrchestrationResult(response=provider_response, citations=citations, artifact=artifact)


async def run_ship30(db: AsyncSession, provider_name: str, topic_message: ChatMessage) -> OrchestrationResult:
    """Retrieve grounding for the topic, draft via the Ship 30 skill, validate,
    and do one automatic repair pass if the draft violates the format rules.
    """
    retrieved = await retrieve(db, topic_message.content)

    if not retrieved:
        # Same rationale as the no-retrieval short-circuit in respond(): don't
        # ask the model to draft a "grounded" essay with nothing to ground it in.
        logger.info("ship30_no_retrieval_short_circuit", provider=provider_name)
        return OrchestrationResult(
            response=ProviderResponse(
                text=(
                    "I don't have transcript material on this topic to draft a grounded Ship 30 "
                    "essay from — try a product/growth topic covered in the knowledge base."
                ),
                provider=provider_name,
                model="n/a (no model call made)",
            ),
            citations=[],
            artifact=None,
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

    artifact = detect_artifact(draft.text)
    citations = [
        {"source_id": c.source_id, "chunk_id": c.chunk_id, "title": c.title, "guest": c.guest, "url": c.url, "score": c.score}
        for c in retrieved
    ]
    return OrchestrationResult(response=draft, citations=citations, artifact=artifact)
