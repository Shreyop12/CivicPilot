import json
from datetime import date
from unittest.mock import AsyncMock

import pytest

from civicpilot.agent.orchestrator import MAX_TOOL_ITERATIONS, Orchestrator
from civicpilot.crosswalk import AgencyCrosswalk, AgencyMapping
from civicpilot.date_resolver import DateResolver


def make_crosswalk():
    return AgencyCrosswalk([
        AgencyMapping("Environmental Protection Agency", "environmental-protection-agency", "068"),
    ])


@pytest.mark.asyncio
async def test_ambiguous_year_query_triggers_elicitation_without_calling_llm():
    llm = AsyncMock()
    fr_impl = AsyncMock()
    usaspending_impl = AsyncMock()
    orchestrator = Orchestrator(llm, fr_impl, usaspending_impl, make_crosswalk(), DateResolver())

    result = await orchestrator.handle_query("What did EPA spend this year?", today=date(2026, 8, 13))

    assert result.needs_clarification is True
    assert "calendar" in result.clarification_question
    assert "fiscal" in result.clarification_question
    llm.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_unambiguous_quarter_query_does_not_trigger_elicitation():
    llm = AsyncMock()
    llm.chat.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "No rules found this quarter."}}],
    }
    fr_impl = AsyncMock()
    usaspending_impl = AsyncMock()
    orchestrator = Orchestrator(llm, fr_impl, usaspending_impl, make_crosswalk(), DateResolver())

    result = await orchestrator.handle_query("What rules were proposed this quarter?", today=date(2026, 8, 13))

    assert result.needs_clarification is False
    llm.chat.assert_awaited()


@pytest.mark.asyncio
async def test_tool_call_resolves_agency_and_returns_cited_answer():
    llm = AsyncMock()
    tool_call_response = {
        "choices": [{"message": {
            "role": "assistant",
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "search_federal_register",
                    "arguments": json.dumps({"action": "search", "agency_name": "Environmental Protection Agency"}),
                },
            }],
        }}],
    }
    final_response = {
        "choices": [{"message": {"role": "assistant", "content": "EPA proposed one rule [doc:2026-12345]."}}],
    }
    llm.chat.side_effect = [tool_call_response, final_response]

    fr_impl = AsyncMock(return_value={"count": 1, "results": [{"document_number": "2026-12345"}]})
    usaspending_impl = AsyncMock()
    orchestrator = Orchestrator(llm, fr_impl, usaspending_impl, make_crosswalk(), DateResolver())

    result = await orchestrator.handle_query("What EPA rules were proposed?", today=date(2026, 8, 13))

    assert result.answer == "EPA proposed one rule [doc:2026-12345]."
    fr_impl.assert_awaited_once_with(
        action="search", agency_slug="environmental-protection-agency",
        doc_type=None, start_date=None, end_date=None, document_number=None,
        per_page=5,
    )


@pytest.mark.asyncio
async def test_unverified_agency_match_is_flagged_in_tool_result():
    llm = AsyncMock()
    tool_call_response = {
        "choices": [{"message": {
            "role": "assistant",
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "search_federal_register",
                    "arguments": json.dumps({"action": "search", "agency_name": "Enviromental Protection Agncy"}),
                },
            }],
        }}],
    }
    final_response = {"choices": [{"message": {"role": "assistant", "content": "No citable results [doc:none]."}}]}
    llm.chat.side_effect = [tool_call_response, final_response]

    fr_impl = AsyncMock(return_value={"count": 0, "results": []})
    usaspending_impl = AsyncMock()
    orchestrator = Orchestrator(llm, fr_impl, usaspending_impl, make_crosswalk(), DateResolver())

    await orchestrator.handle_query("What rules did the EPA propose?", today=date(2026, 8, 13))

    second_call_messages = llm.chat.call_args_list[1].args[0]
    tool_result_message = next(m for m in second_call_messages if m.get("role") == "tool")
    sent_tool_result = json.loads(tool_result_message["content"])
    assert sent_tool_result["agency_match_verified"] is False
    assert sent_tool_result["agency_match_used"] == "Environmental Protection Agency"


@pytest.mark.asyncio
async def test_uncited_claims_are_dropped_from_final_answer():
    llm = AsyncMock()
    llm.chat.return_value = {"choices": [{"message": {
        "role": "assistant",
        "content": "EPA proposed a rule [doc:2026-1]. The agency also secretly doubled its budget overnight.",
    }}]}
    fr_impl = AsyncMock()
    usaspending_impl = AsyncMock()
    orchestrator = Orchestrator(llm, fr_impl, usaspending_impl, make_crosswalk(), DateResolver())

    result = await orchestrator.handle_query("What did EPA propose?", today=date(2026, 8, 13))

    assert "[doc:2026-1]" in result.answer
    assert "secretly doubled" not in result.answer
    assert len(result.dropped_claims) == 1


@pytest.mark.asyncio
async def test_empty_final_answer_asks_for_clarification_instead_of_going_blank():
    """Regression case reported live 2026-08-18: the model stopped calling
    tools (so the 'no tool_calls' early-return path fired, not the
    iteration-budget-exhausted path) but returned no content at all. That
    path returned OrchestratorResult(answer="", dropped_claims=[]) with
    needs_clarification left False — the frontend rendered a blank answer
    bubble with no error and no explanation. The iteration-exhausted path
    already falls back to needs_clarification for an empty answer; the
    early-return path must do the same instead of silently returning nothing.
    """
    llm = AsyncMock()
    llm.chat.return_value = {"choices": [{"message": {"role": "assistant", "content": None}}]}
    fr_impl = AsyncMock()
    usaspending_impl = AsyncMock()
    orchestrator = Orchestrator(llm, fr_impl, usaspending_impl, make_crosswalk(), DateResolver())

    result = await orchestrator.handle_query("What is EPA?", today=date(2026, 8, 13))

    assert result.answer == ""
    assert result.needs_clarification is True
    assert result.clarification_question


@pytest.mark.asyncio
async def test_orchestrator_can_dispatch_bulk_download_actions():
    llm = AsyncMock()
    tool_call_response = {
        "choices": [{"message": {
            "role": "assistant",
            "tool_calls": [{
                "id": "call_bulk",
                "function": {"name": "query_usaspending", "arguments": json.dumps({
                    "action": "submit_bulk_download", "agency_name": "Environmental Protection Agency",
                    "start_date": "2026-01-01", "end_date": "2026-03-31",
                })},
            }],
        }}],
    }
    final_response = {"choices": [{"message": {"role": "assistant", "content": "Export started [award:job-1]."}}]}
    llm.chat.side_effect = [tool_call_response, final_response]

    fr_impl = AsyncMock()
    usaspending_impl = AsyncMock(return_value={"status": "pending", "job_id": "job-1"})
    orchestrator = Orchestrator(llm, fr_impl, usaspending_impl, make_crosswalk(), DateResolver())

    await orchestrator.handle_query("Export all EPA awards this quarter.", today=date(2026, 8, 13))

    usaspending_impl.assert_awaited_once_with(
        action="submit_bulk_download", toptier_code="068",
        start_date="2026-01-01", end_date="2026-03-31",
        award_id=None, fiscal_year=None, job_id=None,
    )


@pytest.mark.asyncio
async def test_exhausting_tool_iteration_budget_asks_for_narrower_query():
    llm = AsyncMock()
    looping_response = {"choices": [{"message": {
        "role": "assistant",
        "tool_calls": [{
            "id": "call_x",
            "function": {"name": "search_federal_register", "arguments": json.dumps({"action": "search"})},
        }],
    }}]}
    llm.chat.return_value = looping_response
    fr_impl = AsyncMock(return_value={"count": 0, "results": []})
    usaspending_impl = AsyncMock()
    orchestrator = Orchestrator(llm, fr_impl, usaspending_impl, make_crosswalk(), DateResolver())

    result = await orchestrator.handle_query("Tell me everything about everything.", today=date(2026, 8, 13))

    assert result.needs_clarification is True
    assert llm.chat.await_count == MAX_TOOL_ITERATIONS + 1


@pytest.mark.asyncio
async def test_handle_query_inserts_history_between_system_and_new_user_message():
    llm = AsyncMock()
    llm.chat.return_value = {"choices": [{"message": {"role": "assistant", "content": "Fine [doc:1]."}}]}
    fr_impl = AsyncMock()
    usaspending_impl = AsyncMock()
    orchestrator = Orchestrator(llm, fr_impl, usaspending_impl, make_crosswalk(), DateResolver())
    prior_history = [
        {"role": "user", "content": "What did EPA spend last period?"},
        {"role": "assistant", "content": "EPA spent $1B [award:1]."},
    ]

    await orchestrator.handle_query(
        "Are there any newer rules?", today=date(2026, 8, 13), history=prior_history,
    )

    sent_messages = llm.chat.call_args.args[0]
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[1] == prior_history[0]
    assert sent_messages[2] == prior_history[1]
    assert sent_messages[3] == {"role": "user", "content": "Are there any newer rules?"}


@pytest.mark.asyncio
async def test_reasoning_trace_is_not_carried_forward_in_history():
    """Regression case found live on 2026-08-18: gpt-oss models (unlike the
    prior llama-3.3-70b-versatile default) return a verbose 'reasoning'/
    'reasoning_details' trace alongside every tool-calling message. Carrying
    that raw trace forward in conversation history on every subsequent
    iteration compounds token usage fast enough to blow Groq's TPM limit
    within a single multi-tool-call query, turning an ordinary question into
    a 413/429 failure. Only the fields the chat-completions API contract
    actually needs (role, content, tool_calls) should be kept in history.
    """
    llm = AsyncMock()
    tool_call_response = {
        "choices": [{"message": {
            "role": "assistant",
            "content": None,
            "reasoning": "Lengthy chain-of-thought the model doesn't need repeated back to it.",
            "reasoning_details": [{"type": "reasoning.text", "text": "..."}],
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "search_federal_register",
                    "arguments": json.dumps({"action": "search", "agency_name": "Environmental Protection Agency"}),
                },
            }],
        }}],
    }
    final_response = {
        "choices": [{"message": {"role": "assistant", "content": "EPA proposed one rule [doc:2026-12345]."}}],
    }
    llm.chat.side_effect = [tool_call_response, final_response]

    fr_impl = AsyncMock(return_value={"count": 1, "results": [{"document_number": "2026-12345"}]})
    usaspending_impl = AsyncMock()
    orchestrator = Orchestrator(llm, fr_impl, usaspending_impl, make_crosswalk(), DateResolver())

    await orchestrator.handle_query("What is EPA?", today=date(2026, 8, 13))

    second_call_messages = llm.chat.call_args_list[1].args[0]
    assistant_message = next(m for m in second_call_messages if m.get("role") == "assistant")
    assert "reasoning" not in assistant_message
    assert "reasoning_details" not in assistant_message
    assert assistant_message["tool_calls"] == tool_call_response["choices"][0]["message"]["tool_calls"]
