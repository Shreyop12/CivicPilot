import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "openai/gpt-oss-20b:free"

PRIMARY_MAX_RETRIES = 2
PRIMARY_BACKOFF_SECONDS = 1.0


class _ChatCompletionsClient:
    """OpenAI-compatible chat-completions client, parameterized by provider."""

    def __init__(self, http_client: httpx.AsyncClient, base_url: str, api_key: str, model: str):
        self._http = http_client
        self._base_url = base_url
        self._api_key = api_key
        self._model = model

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        body: dict[str, object] = {"model": self._model, "messages": messages}
        if tools:
            body["tools"] = tools
        response = await self._http.post(
            f"{self._base_url}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        response.raise_for_status()
        return response.json()


class GroqClient(_ChatCompletionsClient):
    def __init__(self, http_client: httpx.AsyncClient, api_key: str, model: str = DEFAULT_MODEL):
        super().__init__(http_client, GROQ_BASE_URL, api_key, model)


class OpenRouterClient(_ChatCompletionsClient):
    def __init__(self, http_client: httpx.AsyncClient, api_key: str, model: str = OPENROUTER_DEFAULT_MODEL):
        super().__init__(http_client, OPENROUTER_BASE_URL, api_key, model)


class FailoverLLMClient:
    """Wraps a primary and fallback chat-completions client on separate provider
    infra. Rate limits (429) on the primary are retried with short backoff; any
    error that survives those retries — including a non-429 error or a network
    fault — fails over to the fallback client for that call."""

    def __init__(
        self,
        primary,
        fallback,
        max_primary_retries: int = PRIMARY_MAX_RETRIES,
        backoff_seconds: float = PRIMARY_BACKOFF_SECONDS,
    ):
        self._primary = primary
        self._fallback = fallback
        self._max_primary_retries = max_primary_retries
        self._backoff_seconds = backoff_seconds

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        attempt = 0
        while True:
            try:
                return await self._primary.chat(messages, tools=tools)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt < self._max_primary_retries:
                    attempt += 1
                    logger.warning(
                        "Primary LLM rate-limited, retry %d/%d in %.1fs",
                        attempt, self._max_primary_retries, self._backoff_seconds * attempt,
                    )
                    await asyncio.sleep(self._backoff_seconds * attempt)
                    continue
                logger.warning(
                    "Primary LLM failed (HTTP %d), failing over to fallback model",
                    exc.response.status_code,
                )
                break
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                logger.warning("Primary LLM request error (%s), failing over to fallback model", exc)
                break
        return await self._fallback.chat(messages, tools=tools)
