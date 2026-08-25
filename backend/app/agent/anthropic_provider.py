import asyncio
from collections.abc import AsyncIterator

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, StreamEvent, TextBlock, query

from app.agent.base import ChatMessage, LLMProvider, ProviderResponse, ProviderTimeoutError, ProviderUnavailableError
from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)


def _format_history(messages: list[ChatMessage]) -> str:
    """The Claude Agent SDK's query() takes one prompt string, not a chat-messages
    array (its interface is task-oriented, not turn-oriented) — so history is
    composed into a transcript here. This keeps our own DB the source of truth
    for conversation state instead of relying on the SDK's own session/resume
    mechanism, which would require persisting SDK-internal session ids alongside
    our own.
    """
    lines = []
    for m in messages[:-1]:
        speaker = "User" if m.role == "user" else "Assistant"
        lines.append(f"{speaker}: {m.content}")
    if lines:
        history = "\n\n".join(lines)
        return f"Prior conversation:\n{history}\n\nNew user message:\n{messages[-1].content}"
    return messages[-1].content


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.model_name = self.settings.anthropic_model

    async def is_available(self) -> bool:
        return bool(self.settings.anthropic_api_key)

    def _options(self, system_prompt: str, *, streaming: bool) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=self.settings.anthropic_model,
            # No filesystem/bash/network tools: this is a grounded-chat generation
            # call, not a coding agent, and the input is untrusted end-user text.
            # `tools=[]` is what actually disables built-in tools from being
            # offered at all — `allowed_tools` only controls which *offered*
            # tools skip a permission prompt, it doesn't restrict what's
            # offered, so tools=[] is required here, not optional. "dontAsk"
            # (not "deny" — not a real PermissionMode value) means nothing
            # gets prompted for and anything not pre-approved is denied,
            # which is moot anyway since nothing is pre-approved and no tools
            # exist to call. max_turns=1 additionally caps this to a single
            # generation turn as defense in depth against any agentic looping.
            tools=[],
            allowed_tools=[],
            permission_mode="dontAsk",
            max_turns=1,
            # SDKPartialAssistantMessage (surfaced here as StreamEvent) events
            # only get emitted when this is set — otherwise query() only
            # yields the complete AssistantMessage once Claude finishes the
            # whole turn, which is fine for generate() but defeats the point
            # of generate_stream().
            include_partial_messages=streaming,
        )

    async def generate(self, system_prompt: str, messages: list[ChatMessage]) -> ProviderResponse:
        if not await self.is_available():
            raise ProviderUnavailableError("ANTHROPIC_API_KEY is not configured")

        prompt = _format_history(messages)
        options = self._options(system_prompt, streaming=False)

        try:
            collected: list[str] = []

            async def _run() -> None:
                async for message in query(prompt=prompt, options=options):
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                collected.append(block.text)

            await asyncio.wait_for(_run(), timeout=self.settings.provider_timeout_seconds)
        except TimeoutError as exc:
            logger.error("anthropic_timeout")
            raise ProviderTimeoutError("Claude Agent SDK call timed out") from exc
        except Exception as exc:
            logger.error("anthropic_call_failed", error=str(exc))
            raise ProviderUnavailableError(f"Claude Agent SDK call failed: {exc}") from exc

        return ProviderResponse(text="".join(collected).strip(), provider=self.name, model=self.model_name)

    async def generate_stream(self, system_prompt: str, messages: list[ChatMessage]) -> AsyncIterator[str]:
        if not await self.is_available():
            raise ProviderUnavailableError("ANTHROPIC_API_KEY is not configured")

        prompt = _format_history(messages)
        options = self._options(system_prompt, streaming=True)

        # asyncio.wait_for around each __anext__() call (rather than around the
        # whole query()) times out on a stalled stream without capping a
        # reply that's still steadily producing events — same idle-timeout
        # rationale as OllamaProvider.generate_stream.
        stream = query(prompt=prompt, options=options).__aiter__()
        try:
            while True:
                try:
                    message = await asyncio.wait_for(stream.__anext__(), timeout=self.settings.provider_timeout_seconds)
                except StopAsyncIteration:
                    break

                if not isinstance(message, StreamEvent):
                    continue
                event = message.event
                if event.get("type") != "content_block_delta":
                    continue
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    yield delta["text"]
        except TimeoutError as exc:
            logger.error("anthropic_stream_timeout")
            raise ProviderTimeoutError("Claude Agent SDK call timed out") from exc
        except Exception as exc:
            logger.error("anthropic_stream_failed", error=str(exc))
            raise ProviderUnavailableError(f"Claude Agent SDK call failed: {exc}") from exc
