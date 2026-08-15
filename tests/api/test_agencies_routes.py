from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest

from civicpilot.api.app import create_app
from civicpilot.api.deps import get_components
from civicpilot.api.routes.agencies import build_dashboard
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


def make_fake_components_with_data():
    components = make_fake_components()
    components.usaspending_impl = AsyncMock(
        side_effect=[
            {"obligations": 27274197006.76},
            {"obligations": 29100000000.0},
            {"obligations": 10797760149.61},
        ]
    )
    components.fr_impl = AsyncMock(return_value={
        "count": 1,
        "results": [{
            "document_number": "2026-16627",
            "title": "National Emission Standards",
            "type": "RULE",
            "publication_date": "2026-08-01",
            "html_url": "https://www.federalregister.gov/documents/2026-16627",
        }],
    })
    return components


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


@pytest.mark.asyncio
async def test_build_dashboard_returns_three_fiscal_years_with_current_marked_partial():
    components = make_fake_components_with_data()

    dashboard = await build_dashboard(components, "068", today=date(2026, 8, 14))

    assert [o.fiscal_year for o in dashboard.obligations] == [2024, 2025, 2026]
    assert dashboard.obligations[-1].partial is True
    assert dashboard.obligations[0].partial is False
    assert dashboard.obligations[-1].amount == 10797760149.61
    components.usaspending_impl.assert_any_await(
        action="spending_by_agency", toptier_code="068", fiscal_year=2026,
    )


@pytest.mark.asyncio
async def test_build_dashboard_maps_fr_search_results_to_rules():
    components = make_fake_components_with_data()

    dashboard = await build_dashboard(components, "068", today=date(2026, 8, 14))

    assert len(dashboard.rules) == 1
    assert dashboard.rules[0].document_number == "2026-16627"
    components.fr_impl.assert_awaited_once_with(
        action="search", agency_slug="environmental-protection-agency", doc_type="RULE",
        start_date="2025-08-14", end_date="2026-08-14",
    )


@pytest.mark.asyncio
async def test_dashboard_endpoint_returns_404_for_unknown_toptier_code():
    app = create_app()
    app.dependency_overrides[get_components] = make_fake_components_with_data

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agencies/999/dashboard")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dashboard_endpoint_returns_full_payload():
    app = create_app()
    app.dependency_overrides[get_components] = make_fake_components_with_data

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agencies/068/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Environmental Protection Agency"
    assert len(body["obligations"]) == 3
    assert len(body["rules"]) == 1
