from abc import ABC, abstractmethod
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

    @abstractmethod
    async def generate(self, system_prompt: str, messages: list[ChatMessage]) -> ProviderResponse: ...

    @abstractmethod
    async def is_available(self) -> bool: ...
