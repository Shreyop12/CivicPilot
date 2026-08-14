import json

import httpx
import pytest
import respx

from civicpilot.agent.llm_client import DEFAULT_MODEL, GROQ_BASE_URL, GroqClient


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
