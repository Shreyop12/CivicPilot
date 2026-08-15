import httpx
import pytest
import respx

from civicpilot.cache import QueryCache
from civicpilot.clients.fr_client import FR_BASE_URL, FederalRegisterClient


@pytest.mark.asyncio
@respx.mock
async def test_search_documents_returns_parsed_json():
    respx.get(f"{FR_BASE_URL}/documents.json").mock(
        return_value=httpx.Response(200, json={"count": 1, "results": [{"document_number": "2026-12345"}]})
    )
    async with httpx.AsyncClient() as http:
        client = FederalRegisterClient(http, QueryCache())
        result = await client.search_documents(agency_slug="environmental-protection-agency")
    assert result["count"] == 1
    assert result["results"][0]["document_number"] == "2026-12345"


@pytest.mark.asyncio
@respx.mock
async def test_search_documents_requests_only_needed_fields():
    """The FR API's default document representation includes abstract/excerpts/
    extra URL fields that bloat a single tool result to ~39KB (~10K tokens),
    enough on its own to blow Groq's 12K TPM budget. None of those fields are
    used downstream, so the request must scope to fields[] the tool actually
    consumes.
    """
    route = respx.get(f"{FR_BASE_URL}/documents.json").mock(
        return_value=httpx.Response(200, json={"count": 0, "results": []})
    )
    async with httpx.AsyncClient() as http:
        client = FederalRegisterClient(http, QueryCache())
        await client.search_documents(agency_slug="environmental-protection-agency")
    request = route.calls[0].request
    query = str(request.url)
    assert "fields%5B%5D=document_number" in query
    assert "fields%5B%5D=title" in query
    assert "abstract" not in query
    assert "excerpts" not in query


@pytest.mark.asyncio
@respx.mock
async def test_search_documents_uses_cache_on_second_call():
    route = respx.get(f"{FR_BASE_URL}/documents.json").mock(
        return_value=httpx.Response(200, json={"count": 0, "results": []})
    )
    async with httpx.AsyncClient() as http:
        cache = QueryCache()
        client = FederalRegisterClient(http, cache)
        await client.search_documents(agency_slug="epa")
        await client.search_documents(agency_slug="epa")
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_get_document_returns_parsed_json():
    respx.get(f"{FR_BASE_URL}/documents/2026-12345.json").mock(
        return_value=httpx.Response(200, json={"document_number": "2026-12345", "title": "Example Rule"})
    )
    async with httpx.AsyncClient() as http:
        client = FederalRegisterClient(http, QueryCache())
        result = await client.get_document("2026-12345")
    assert result["title"] == "Example Rule"


@pytest.mark.asyncio
@respx.mock
async def test_search_documents_raises_on_http_error():
    respx.get(f"{FR_BASE_URL}/documents.json").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as http:
        client = FederalRegisterClient(http, QueryCache())
        with pytest.raises(httpx.HTTPStatusError):
            await client.search_documents()
