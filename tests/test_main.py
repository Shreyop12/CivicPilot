import httpx
import pytest

from civicpilot.agent.llm_client import FailoverLLMClient, GroqClient
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
        assert isinstance(components.orchestrator._llm, GroqClient)
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
        assert isinstance(components.orchestrator._llm, FailoverLLMClient)
    finally:
        await components.http.aclose()


@pytest.mark.asyncio
async def test_build_orchestrator_raises_systemexit_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr("civicpilot.main.load_dotenv", lambda *args, **kwargs: None)
    with pytest.raises(SystemExit):
        await build_orchestrator()
