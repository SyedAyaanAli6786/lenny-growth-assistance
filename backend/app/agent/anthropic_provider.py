import asyncio

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

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

    async def is_available(self) -> bool:
        return bool(self.settings.anthropic_api_key)

    async def generate(self, system_prompt: str, messages: list[ChatMessage]) -> ProviderResponse:
        if not await self.is_available():
            raise ProviderUnavailableError("ANTHROPIC_API_KEY is not configured")

        prompt = _format_history(messages)
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=self.settings.anthropic_model,
            # No filesystem/bash/network tools: this is a grounded-chat generation
            # call, not a coding agent, and the input is untrusted end-user text.
            allowed_tools=[],
            permission_mode="deny",
        )

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

        return ProviderResponse(text="".join(collected).strip(), provider=self.name, model=self.settings.anthropic_model)
