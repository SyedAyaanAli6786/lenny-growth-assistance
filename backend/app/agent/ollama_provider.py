import httpx

from app.agent.base import ChatMessage, LLMProvider, ProviderResponse, ProviderTimeoutError, ProviderUnavailableError
from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.settings.ollama_base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def generate(self, system_prompt: str, messages: list[ChatMessage]) -> ProviderResponse:
        payload_messages = [{"role": "system", "content": system_prompt}]
        payload_messages.extend({"role": m.role, "content": m.content} for m in messages)

        url = f"{self.settings.ollama_base_url}/api/chat"
        payload = {"model": self.settings.ollama_model, "messages": payload_messages, "stream": False}

        try:
            async with httpx.AsyncClient(timeout=self.settings.provider_timeout_seconds) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.error("ollama_timeout")
            raise ProviderTimeoutError("Ollama call timed out") from exc
        except httpx.HTTPError as exc:
            logger.error("ollama_call_failed", error=str(exc))
            raise ProviderUnavailableError(f"Ollama call failed: {exc}") from exc

        data = response.json()
        text = data.get("message", {}).get("content", "")
        return ProviderResponse(text=text.strip(), provider=self.name, model=self.settings.ollama_model)
