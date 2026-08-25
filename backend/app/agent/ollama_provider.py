import json
from collections.abc import AsyncIterator

import httpx

from app.agent.base import ChatMessage, LLMProvider, ProviderResponse, ProviderTimeoutError, ProviderUnavailableError
from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.model_name = self.settings.ollama_model

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.settings.ollama_base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    def _payload(self, system_prompt: str, messages: list[ChatMessage], stream: bool) -> dict:
        payload_messages = [{"role": "system", "content": system_prompt}]
        payload_messages.extend({"role": m.role, "content": m.content} for m in messages)
        return {
            "model": self.settings.ollama_model,
            "messages": payload_messages,
            "stream": stream,
            # We only ever read message.content, never message.thinking, so a
            # hybrid-reasoning model's hidden thinking pass is pure overhead
            # here — measured 15x latency on a trivial prompt with a
            # thinking-capable model (qwen3:8b: ~36s -> ~2.5s), enough to push
            # the longer Ship 30 prompt past provider_timeout_seconds
            # entirely. Non-thinking models (e.g. llama3.1:8b) accept and
            # ignore this flag with no effect — verified before enabling it
            # unconditionally.
            "think": False,
        }

    async def generate(self, system_prompt: str, messages: list[ChatMessage]) -> ProviderResponse:
        url = f"{self.settings.ollama_base_url}/api/chat"

        try:
            async with httpx.AsyncClient(timeout=self.settings.provider_timeout_seconds) as client:
                response = await client.post(url, json=self._payload(system_prompt, messages, stream=False))
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.error("ollama_timeout")
            raise ProviderTimeoutError("Ollama call timed out") from exc
        except httpx.HTTPError as exc:
            logger.error("ollama_call_failed", error=str(exc))
            raise ProviderUnavailableError(f"Ollama call failed: {exc}") from exc

        data = response.json()
        text = data.get("message", {}).get("content", "")
        return ProviderResponse(text=text.strip(), provider=self.name, model=self.model_name)

    async def generate_stream(self, system_prompt: str, messages: list[ChatMessage]) -> AsyncIterator[str]:
        url = f"{self.settings.ollama_base_url}/api/chat"

        # timeout applies per network operation (connect/read/write), not to
        # the call as a whole — a read timeout fires only if no new line
        # arrives within provider_timeout_seconds, so a reply that's still
        # steadily streaming tokens past that mark isn't killed, only a
        # genuinely stalled one is.
        try:
            async with httpx.AsyncClient(timeout=self.settings.provider_timeout_seconds) as client:
                async with client.stream(
                    "POST", url, json=self._payload(system_prompt, messages, stream=True)
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        chunk = json.loads(line)
                        piece = chunk.get("message", {}).get("content", "")
                        if piece:
                            yield piece
                        if chunk.get("done"):
                            break
        except httpx.TimeoutException as exc:
            logger.error("ollama_stream_timeout")
            raise ProviderTimeoutError("Ollama call timed out") from exc
        except httpx.HTTPError as exc:
            logger.error("ollama_stream_failed", error=str(exc))
            raise ProviderUnavailableError(f"Ollama call failed: {exc}") from exc
