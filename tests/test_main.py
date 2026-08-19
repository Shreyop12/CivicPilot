import httpx
import pytest

from civicpilot.agent.llm_client import FailoverLLMClient, GroqClient, OpenRouterClient
from civicpilot.agent.orchestrator import Orchestrator
from civicpilot.crosswalk import AgencyCrosswalk
from civicpilot.main import build_orchestrator


@pytest.mark.asyncio
async def test_build_orchestrator_wires_all_components(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("civicpilot.main.load_dotenv", lambda *args, **kwargs: None)
    components = await build_orchestrator()
    try:
        assert isinstance(components.orchestrator, Orchestrator)
        assert isinstance(components.http, httpx.AsyncClient)
        assert isinstance(components.orchestrator._tool_llm, GroqClient)
        assert isinstance(components.orchestrator._answer_llm, GroqClient)
        assert isinstance(components.crosswalk, AgencyCrosswalk)
        assert callable(components.fr_impl)
        assert callable(components.usaspending_impl)
    finally:
        await components.http.aclose()


@pytest.mark.asyncio
async def test_build_orchestrator_wires_failover_llm_when_openrouter_key_present(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setattr("civicpilot.main.load_dotenv", lambda *args, **kwargs: None)
    components = await build_orchestrator()
    try:
        assert isinstance(components.orchestrator._tool_llm, FailoverLLMClient)
        assert isinstance(components.orchestrator._answer_llm, FailoverLLMClient)
    finally:
        await components.http.aclose()


@pytest.mark.asyncio
async def test_build_orchestrator_routes_tool_calls_to_small_model_and_answers_to_large_model(monkeypatch):
    """The tool-selection loop and the final answer are deliberately routed
    to different models: tool_llm tries the small OpenRouter free model
    first (relieving Groq's TPM budget across the repeated, schema-heavy
    loop calls), falling back to Groq if OpenRouter is down; answer_llm
    tries Groq first for answer quality, falling back to OpenRouter. Both
    directions are covered so an outage on either provider degrades rather
    than fails outright."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setattr("civicpilot.main.load_dotenv", lambda *args, **kwargs: None)
    components = await build_orchestrator()
    try:
        tool_llm = components.orchestrator._tool_llm
        answer_llm = components.orchestrator._answer_llm
        assert isinstance(tool_llm._primary, OpenRouterClient)
        assert isinstance(tool_llm._fallback, GroqClient)
        assert isinstance(answer_llm._primary, GroqClient)
        assert isinstance(answer_llm._fallback, OpenRouterClient)
    finally:
        await components.http.aclose()


@pytest.mark.asyncio
async def test_build_orchestrator_raises_systemexit_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr("civicpilot.main.load_dotenv", lambda *args, **kwargs: None)
    with pytest.raises(SystemExit):
        await build_orchestrator()
