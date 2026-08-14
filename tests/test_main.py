import pytest

from civicpilot.agent.orchestrator import Orchestrator
from civicpilot.main import build_orchestrator


@pytest.mark.asyncio
async def test_build_orchestrator_wires_all_components(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    orchestrator = await build_orchestrator()
    assert isinstance(orchestrator, Orchestrator)
