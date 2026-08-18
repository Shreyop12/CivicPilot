from unittest.mock import AsyncMock

import httpx
import pytest

from civicpilot.agent.orchestrator import OrchestratorResult
from civicpilot.api.app import create_app
from civicpilot.api.deps import get_components, get_conversations


def make_fake_components(handle_query_result):
    class FakeComponents:
        orchestrator = AsyncMock()
        fr_impl = AsyncMock()
        usaspending_impl = AsyncMock()
        crosswalk = None

    components = FakeComponents()
    components.orchestrator.handle_query = AsyncMock(return_value=handle_query_result)
    return components


@pytest.mark.asyncio
async def test_chat_returns_answer_and_stores_compact_history():
    result = OrchestratorResult(answer="EPA spent $1B [award:1].", dropped_claims=["unsupported claim"])
    components = make_fake_components(result)
    conversations: dict = {}

    app = create_app()
    app.dependency_overrides[get_components] = lambda: components
    app.dependency_overrides[get_conversations] = lambda: conversations

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat", json={"conversation_id": "conv-1", "message": "What did EPA spend?"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "EPA spent $1B [award:1]."
    assert body["dropped_claims"] == ["unsupported claim"]
    assert body["needs_clarification"] is False

    assert conversations["conv-1"] == [
        {"role": "user", "content": "What did EPA spend?"},
        {"role": "assistant", "content": "EPA spent $1B [award:1]."},
    ]
    components.orchestrator.handle_query.assert_awaited_once_with("What did EPA spend?", history=[])


@pytest.mark.asyncio
async def test_chat_passes_prior_history_and_appends_clarification_as_assistant_turn():
    result = OrchestratorResult(
        answer="", needs_clarification=True, clarification_question="Calendar or fiscal year?",
    )
    components = make_fake_components(result)
    prior = [{"role": "user", "content": "What did EPA spend this year?"}]
    conversations = {"conv-2": prior}

    app = create_app()
    app.dependency_overrides[get_components] = lambda: components
    app.dependency_overrides[get_conversations] = lambda: conversations

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat", json={"conversation_id": "conv-2", "message": "This year"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["needs_clarification"] is True
    assert body["clarification_question"] == "Calendar or fiscal year?"

    components.orchestrator.handle_query.assert_awaited_once_with("This year", history=prior)
    assert conversations["conv-2"][-1] == {"role": "assistant", "content": "Calendar or fiscal year?"}


@pytest.mark.asyncio
async def test_chat_returns_clean_503_when_llm_providers_are_unavailable():
    """Regression case found live 2026-08-18: when both the primary and
    fallback LLM providers fail for a request (e.g. Groq TPM-limited and the
    OpenRouter fallback also upstream-rate-limited), handle_query raises
    rather than returning an OrchestratorResult. Uncaught, that crashed the
    route with a raw 500 and left conversation history unmodified but the
    request state ambiguous. The route should catch it and return a clean,
    loggable 503 instead of leaking an unhandled exception.
    """
    components = make_fake_components(None)
    components.orchestrator.handle_query = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "429", request=httpx.Request("POST", "http://x"), response=httpx.Response(429),
        )
    )
    conversations: dict = {}

    app = create_app()
    app.dependency_overrides[get_components] = lambda: components
    app.dependency_overrides[get_conversations] = lambda: conversations

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat", json={"conversation_id": "conv-3", "message": "What is EPA?"},
        )

    assert response.status_code == 503
    assert "conv-3" not in conversations
