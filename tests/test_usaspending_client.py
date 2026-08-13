import httpx
import pytest
import respx

from civicpilot.cache import QueryCache
from civicpilot.clients.usaspending_client import USASPENDING_BASE_URL, USASpendingClient


@pytest.mark.asyncio
@respx.mock
async def test_search_awards_returns_parsed_json():
    respx.post(f"{USASPENDING_BASE_URL}/search/spending_by_award/").mock(
        return_value=httpx.Response(200, json={"results": [{"Award ID": "AWD-1"}]})
    )
    async with httpx.AsyncClient() as http:
        client = USASpendingClient(http, QueryCache())
        result = await client.search_awards(toptier_code="068", start_date="2026-01-01", end_date="2026-03-31")
    assert result["results"][0]["Award ID"] == "AWD-1"


@pytest.mark.asyncio
@respx.mock
async def test_search_awards_uses_cache_on_second_call():
    route = respx.post(f"{USASPENDING_BASE_URL}/search/spending_by_award/").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    async with httpx.AsyncClient() as http:
        cache = QueryCache()
        client = USASpendingClient(http, cache)
        await client.search_awards(toptier_code="068", start_date="2026-01-01", end_date="2026-03-31")
        await client.search_awards(toptier_code="068", start_date="2026-01-01", end_date="2026-03-31")
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_get_award_returns_parsed_json():
    respx.get(f"{USASPENDING_BASE_URL}/awards/AWD-1/").mock(
        return_value=httpx.Response(200, json={"id": "AWD-1", "total_obligation": 1000})
    )
    async with httpx.AsyncClient() as http:
        client = USASpendingClient(http, QueryCache())
        result = await client.get_award("AWD-1")
    assert result["total_obligation"] == 1000


@pytest.mark.asyncio
@respx.mock
async def test_spending_by_agency_returns_parsed_json():
    respx.get(f"{USASPENDING_BASE_URL}/agency/068/awards/").mock(
        return_value=httpx.Response(200, json={"toptier_code": "068", "total_obligations": 4200000})
    )
    async with httpx.AsyncClient() as http:
        client = USASpendingClient(http, QueryCache())
        result = await client.spending_by_agency(toptier_code="068", fiscal_year=2026)
    assert result["total_obligations"] == 4200000


@pytest.mark.asyncio
@respx.mock
async def test_search_awards_raises_on_http_error():
    respx.post(f"{USASPENDING_BASE_URL}/search/spending_by_award/").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as http:
        client = USASpendingClient(http, QueryCache())
        with pytest.raises(httpx.HTTPStatusError):
            await client.search_awards(toptier_code="068", start_date="2026-01-01", end_date="2026-03-31")
