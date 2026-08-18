from unittest.mock import AsyncMock

import pytest

from civicpilot.servers.fr_server import build_fr_server


@pytest.mark.asyncio
async def test_search_action_calls_client_search_documents():
    client = AsyncMock()
    client.search_documents.return_value = {"count": 0, "results": []}
    server = build_fr_server(client)

    result = await server._search_documents_impl(action="search", agency_slug="epa")

    assert result == {"count": 0, "results": []}
    client.search_documents.assert_awaited_once_with(
        agency_slug="epa", doc_type=None, start_date=None, end_date=None, per_page=20,
    )


@pytest.mark.asyncio
async def test_search_action_forwards_explicit_per_page():
    """The chat agent passes a smaller per_page than the dashboard's default
    20 to keep tool-call results from pushing a multi-search conversation
    over Groq's TPM limit (found live 2026-08-18) — must actually thread
    through this closure, not just the module-level function.
    """
    client = AsyncMock()
    client.search_documents.return_value = {"count": 0, "results": []}
    server = build_fr_server(client)

    await server._search_documents_impl(action="search", agency_slug="epa", per_page=5)

    client.search_documents.assert_awaited_once_with(
        agency_slug="epa", doc_type=None, start_date=None, end_date=None, per_page=5,
    )


@pytest.mark.asyncio
async def test_get_action_calls_client_get_document():
    client = AsyncMock()
    client.get_document.return_value = {"document_number": "2026-1"}
    server = build_fr_server(client)

    result = await server._search_documents_impl(action="get", document_number="2026-1")

    assert result == {"document_number": "2026-1"}
    client.get_document.assert_awaited_once_with("2026-1")


@pytest.mark.asyncio
async def test_get_action_without_document_number_raises():
    client = AsyncMock()
    server = build_fr_server(client)
    with pytest.raises(ValueError, match="document_number is required"):
        await server._search_documents_impl(action="get")


@pytest.mark.asyncio
async def test_unsupported_action_raises_actionable_error():
    client = AsyncMock()
    server = build_fr_server(client)
    with pytest.raises(ValueError, match="unsupported action"):
        await server._search_documents_impl(action="delete")
