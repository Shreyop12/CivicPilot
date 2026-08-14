import httpx

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "moonshotai/kimi-k2-instruct"


class GroqClient:
    def __init__(self, http_client: httpx.AsyncClient, api_key: str, model: str = DEFAULT_MODEL):
        self._http = http_client
        self._api_key = api_key
        self._model = model

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        body: dict[str, object] = {"model": self._model, "messages": messages}
        if tools:
            body["tools"] = tools
        response = await self._http.post(
            f"{GROQ_BASE_URL}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        response.raise_for_status()
        return response.json()
