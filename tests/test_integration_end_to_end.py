import json

import httpx
import pytest
import respx

from civicpilot.agent.llm_client import GROQ_BASE_URL, GroqClient
from civicpilot.agent.orchestrator import Orchestrator
from civicpilot.cache import QueryCache
from civicpilot.clients.fr_client import FR_BASE_URL, FederalRegisterClient
from civicpilot.clients.usaspending_client import USASPENDING_BASE_URL, USASpendingClient
from civicpilot.clients.usaspending_download_client import USASpendingDownloadClient
from civicpilot.crosswalk import load_default_crosswalk
from civicpilot.date_resolver import DateResolver
from civicpilot.servers.fr_server import build_fr_server
from civicpilot.servers.usaspending_server import build_usaspending_server


@pytest.mark.asyncio
@respx.mock
async def test_flagship_query_returns_cited_answer_from_both_sources():
    fr_route = respx.get(f"{FR_BASE_URL}/documents.json").mock(
        return_value=httpx.Response(200, json={
            "count": 1,
            "results": [{"document_number": "2026-12345", "title": "Emissions Reporting Rule"}],
        })
    )
    usa_route = respx.get(f"{USASPENDING_BASE_URL}/agency/068/awards/").mock(
        return_value=httpx.Response(200, json={"toptier_code": "068", "total_obligations": 4200000})
    )

    first_turn = {
        "choices": [{"message": {
            "role": "assistant",
            "tool_calls": [{
                "id": "call_fr",
                "function": {"name": "search_federal_register", "arguments": json.dumps({
                    "action": "search", "agency_name": "Environmental Protection Agency",
                    "doc_type": "PRORULE", "start_date": "2026-07-01", "end_date": "2026-09-30",
                })},
            }],
        }}],
    }
    second_turn = {
        "choices": [{"message": {
            "role": "assistant",
            "tool_calls": [{
                "id": "call_usa",
                "function": {"name": "query_usaspending", "arguments": json.dumps({
                    "action": "spending_by_agency", "agency_name": "Environmental Protection Agency",
                    "fiscal_year": 2026,
                })},
            }],
        }}],
    }
    final_turn = {
        "choices": [{"message": {
            "role": "assistant",
            "content": (
                "EPA proposed the Emissions Reporting Rule [doc:2026-12345]. "
                "Related agency-wide obligations for FY2026 total $4,200,000 [award:agency-068-fy2026]."
            ),
        }}],
    }
    respx.post(f"{GROQ_BASE_URL}/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json=first_turn),
            httpx.Response(200, json=second_turn),
            httpx.Response(200, json=final_turn),
        ]
    )

    async with httpx.AsyncClient() as http:
        cache = QueryCache()
        fr_server = build_fr_server(FederalRegisterClient(http, cache))
        usaspending_server = build_usaspending_server(
            USASpendingClient(http, cache), USASpendingDownloadClient(http),
        )
        orchestrator = Orchestrator(
            llm=GroqClient(http, api_key="test-key"),
            fr_impl=fr_server._search_documents_impl,
            usaspending_impl=usaspending_server._query_spending_impl,
            crosswalk=load_default_crosswalk(),
            date_resolver=DateResolver(),
        )

        result = await orchestrator.handle_query(
            "What EPA rules were proposed this quarter, and what's the related spending?",
        )

    assert "[doc:2026-12345]" in result.answer
    assert "[award:agency-068-fy2026]" in result.answer
    assert result.needs_clarification is False
    assert fr_route.called
    assert usa_route.called
    assert result.dropped_claims == []
