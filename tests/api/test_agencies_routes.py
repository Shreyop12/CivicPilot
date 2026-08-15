from unittest.mock import AsyncMock

import httpx
import pytest

from civicpilot.api.app import create_app
from civicpilot.api.deps import get_components
from civicpilot.crosswalk import AgencyCrosswalk, AgencyMapping


def make_fake_components():
    class FakeComponents:
        crosswalk = AgencyCrosswalk([
            AgencyMapping("Environmental Protection Agency", "environmental-protection-agency", "068"),
            AgencyMapping("Department of Energy", "energy-department", "089"),
        ])
        fr_impl = AsyncMock()
        usaspending_impl = AsyncMock()
        orchestrator = AsyncMock()

    return FakeComponents()


@pytest.mark.asyncio
async def test_list_agencies_returns_every_crosswalk_entry():
    app = create_app()
    app.dependency_overrides[get_components] = make_fake_components

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agencies")

    assert response.status_code == 200
    names = {entry["name"] for entry in response.json()}
    assert names == {"Environmental Protection Agency", "Department of Energy"}
    epa = next(entry for entry in response.json() if entry["toptier_code"] == "068")
    assert epa["fr_slug"] == "environmental-protection-agency"
