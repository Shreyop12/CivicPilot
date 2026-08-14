import json

import httpx
import pytest
import respx

from civicpilot.agent.llm_client import (
    DEFAULT_MODEL,
    GROQ_BASE_URL,
    OPENROUTER_BASE_URL,
    OPENROUTER_DEFAULT_MODEL,
    FailoverLLMClient,
    GroqClient,
    OpenRouterClient,
)


@pytest.mark.asyncio
@respx.mock
async def test_chat_sends_model_and_messages_and_returns_parsed_response():
    route = respx.post(f"{GROQ_BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "hi"}}]})
    )
    async with httpx.AsyncClient() as http:
        client = GroqClient(http, api_key="test-key")
        result = await client.chat([{"role": "user", "content": "hello"}])
    assert result["choices"][0]["message"]["content"] == "hi"
    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body["model"] == DEFAULT_MODEL


@pytest.mark.asyncio
@respx.mock
async def test_chat_includes_tools_when_provided():
    route = respx.post(f"{GROQ_BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "tool_calls": []}}]})
    )
    tools = [{"type": "function", "function": {"name": "search_documents", "parameters": {}}}]
    async with httpx.AsyncClient() as http:
        client = GroqClient(http, api_key="test-key")
        await client.chat([{"role": "user", "content": "hello"}], tools=tools)
    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body["tools"] == tools


@pytest.mark.asyncio
@respx.mock
async def test_chat_sends_authorization_header():
    respx.post(f"{GROQ_BASE_URL}/chat/completions").mock(return_value=httpx.Response(200, json={"choices": []}))
    async with httpx.AsyncClient() as http:
        client = GroqClient(http, api_key="secret-123")
        await client.chat([{"role": "user", "content": "hi"}])
    request = respx.calls[0].request
    assert request.headers["Authorization"] == "Bearer secret-123"


@pytest.mark.asyncio
@respx.mock
async def test_chat_raises_on_http_error():
    respx.post(f"{GROQ_BASE_URL}/chat/completions").mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    async with httpx.AsyncClient() as http:
        client = GroqClient(http, api_key="bad")
        with pytest.raises(httpx.HTTPStatusError):
            await client.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
@respx.mock
async def test_openrouter_chat_sends_model_and_messages_and_returns_parsed_response():
    route = respx.post(f"{OPENROUTER_BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "hi"}}]})
    )
    async with httpx.AsyncClient() as http:
        client = OpenRouterClient(http, api_key="test-key")
        result = await client.chat([{"role": "user", "content": "hello"}])
    assert result["choices"][0]["message"]["content"] == "hi"
    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body["model"] == OPENROUTER_DEFAULT_MODEL


@pytest.mark.asyncio
@respx.mock
async def test_openrouter_chat_sends_authorization_header():
    respx.post(f"{OPENROUTER_BASE_URL}/chat/completions").mock(return_value=httpx.Response(200, json={"choices": []}))
    async with httpx.AsyncClient() as http:
        client = OpenRouterClient(http, api_key="secret-123")
        await client.chat([{"role": "user", "content": "hi"}])
    request = respx.calls[0].request
    assert request.headers["Authorization"] == "Bearer secret-123"


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com/chat/completions")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(f"{status_code} error", request=request, response=response)


class _StubChatClient:
    """Test double for a chat-completions client: replays queued results in order."""

    def __init__(self, results):
        self._results = list(results)
        self.calls: list[dict] = []

    async def chat(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


SUCCESS = {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
FALLBACK_SUCCESS = {"choices": [{"message": {"role": "assistant", "content": "fallback ok"}}]}


@pytest.mark.asyncio
async def test_failover_uses_primary_on_success_without_touching_fallback():
    primary = _StubChatClient([SUCCESS])
    fallback = _StubChatClient([FALLBACK_SUCCESS])
    client = FailoverLLMClient(primary, fallback, backoff_seconds=0)
    result = await client.chat([{"role": "user", "content": "hi"}])
    assert result == SUCCESS
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 0


@pytest.mark.asyncio
async def test_failover_retries_primary_on_429_then_succeeds_without_fallback():
    primary = _StubChatClient([_http_error(429), SUCCESS])
    fallback = _StubChatClient([FALLBACK_SUCCESS])
    client = FailoverLLMClient(primary, fallback, backoff_seconds=0)
    result = await client.chat([{"role": "user", "content": "hi"}])
    assert result == SUCCESS
    assert len(primary.calls) == 2
    assert len(fallback.calls) == 0


@pytest.mark.asyncio
async def test_failover_switches_to_fallback_after_429_retries_exhausted():
    primary = _StubChatClient([_http_error(429), _http_error(429), _http_error(429)])
    fallback = _StubChatClient([FALLBACK_SUCCESS])
    client = FailoverLLMClient(primary, fallback, max_primary_retries=2, backoff_seconds=0)
    result = await client.chat([{"role": "user", "content": "hi"}])
    assert result == FALLBACK_SUCCESS
    assert len(primary.calls) == 3
    assert len(fallback.calls) == 1


@pytest.mark.asyncio
async def test_failover_switches_to_fallback_immediately_on_5xx_no_retry():
    primary = _StubChatClient([_http_error(503)])
    fallback = _StubChatClient([FALLBACK_SUCCESS])
    client = FailoverLLMClient(primary, fallback, backoff_seconds=0)
    result = await client.chat([{"role": "user", "content": "hi"}])
    assert result == FALLBACK_SUCCESS
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


@pytest.mark.asyncio
async def test_failover_switches_to_fallback_on_network_error():
    primary = _StubChatClient([httpx.ConnectError("boom")])
    fallback = _StubChatClient([FALLBACK_SUCCESS])
    client = FailoverLLMClient(primary, fallback, backoff_seconds=0)
    result = await client.chat([{"role": "user", "content": "hi"}])
    assert result == FALLBACK_SUCCESS
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


@pytest.mark.asyncio
async def test_failover_propagates_when_both_primary_and_fallback_fail():
    primary = _StubChatClient([_http_error(500)])
    fallback = _StubChatClient([_http_error(500)])
    client = FailoverLLMClient(primary, fallback, backoff_seconds=0)
    with pytest.raises(httpx.HTTPStatusError):
        await client.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_failover_passes_tools_through_to_whichever_client_serves_the_call():
    tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
    primary = _StubChatClient([_http_error(500)])
    fallback = _StubChatClient([FALLBACK_SUCCESS])
    client = FailoverLLMClient(primary, fallback, backoff_seconds=0)
    await client.chat([{"role": "user", "content": "hi"}], tools=tools)
    assert primary.calls[0]["tools"] == tools
    assert fallback.calls[0]["tools"] == tools
