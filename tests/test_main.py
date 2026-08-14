import httpx
import pytest

from civicpilot.agent.orchestrator import Orchestrator
from civicpilot.main import build_orchestrator


@pytest.mark.asyncio
async def test_build_orchestrator_wires_all_components(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    orchestrator, http = await build_orchestrator()
    try:
        assert isinstance(orchestrator, Orchestrator)
        assert isinstance(http, httpx.AsyncClient)
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_build_orchestrator_raises_systemexit_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        await build_orchestrator()
