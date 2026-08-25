from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    provider: str
    model: str


class ProviderUnavailableError(RuntimeError):
    """Raised when a provider can't be reached (missing key, connection refused, etc.)."""


class ProviderTimeoutError(RuntimeError):
    """Raised when a provider call exceeds the configured timeout."""


class LLMProvider(ABC):
    """Common interface both the Claude Agent SDK path and the Ollama path implement.

    Retrieval and prompt construction happen upstream in orchestrator.py, so a
    provider's only job is: given a system prompt and message history, return text.
    This keeps behavior identical across the provider toggle.
    """

    name: str
    model_name: str  # set by each implementation's __init__; echoed into ProviderResponse.model

    @abstractmethod
    async def generate(self, system_prompt: str, messages: list[ChatMessage]) -> ProviderResponse: ...

    @abstractmethod
    def generate_stream(self, system_prompt: str, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """Same generation as generate(), but yields text deltas as they arrive
        instead of buffering the full reply — lets the chat UI render tokens
        as they're produced instead of a multi-minute blank wait on CPU-only
        Ollama. Ship 30 drafting still uses generate(): its validator/repair
        pass needs a complete draft before it can check word count/headings/
        takeaway, so there's nothing useful to stream there."""
        ...

    @abstractmethod
    async def is_available(self) -> bool: ...
