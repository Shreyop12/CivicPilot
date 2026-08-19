import json
from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest

from civicpilot.agent.orchestrator import MAX_TOOL_ITERATIONS, Orchestrator
from civicpilot.crosswalk import AgencyCrosswalk, AgencyMapping
from civicpilot.date_resolver import DateResolver

NO_TOOL_CALLS_MESSAGE = {"choices": [{"message": {"role": "assistant", "content": None}}]}


def make_crosswalk():
    return AgencyCrosswalk([
        AgencyMapping("Environmental Protection Agency", "environmental-protection-agency", "068"),
    ])


def make_orchestrator(tool_llm=None, answer_llm=None, fr_impl=None, usaspending_impl=None):
    return Orchestrator(
        tool_llm or AsyncMock(), answer_llm or AsyncMock(),
        fr_impl or AsyncMock(), usaspending_impl or AsyncMock(),
        make_crosswalk(), DateResolver(),
    )


@pytest.mark.asyncio
async def test_ambiguous_year_query_triggers_elicitation_without_calling_llm():
    tool_llm = AsyncMock()
    answer_llm = AsyncMock()
    orchestrator = make_orchestrator(tool_llm, answer_llm)

    result = await orchestrator.handle_query("What did EPA spend this year?", today=date(2026, 8, 13))

    assert result.needs_clarification is True
    assert "calendar" in result.clarification_question
    assert "fiscal" in result.clarification_question
    tool_llm.chat.assert_not_awaited()
    answer_llm.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_unambiguous_quarter_query_does_not_trigger_elicitation():
    tool_llm = AsyncMock()
    tool_llm.chat.return_value = NO_TOOL_CALLS_MESSAGE
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "No rules were proposed this quarter [doc:none]."}}],
    }
    orchestrator = make_orchestrator(tool_llm, answer_llm)

    result = await orchestrator.handle_query("What rules were proposed this quarter?", today=date(2026, 8, 13))

    assert result.needs_clarification is False
    answer_llm.chat.assert_awaited()


@pytest.mark.asyncio
async def test_tool_call_resolves_agency_and_returns_cited_answer():
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
    tool_llm = AsyncMock()
    tool_llm.chat.side_effect = [tool_call_response, NO_TOOL_CALLS_MESSAGE]
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "EPA proposed one rule [doc:2026-12345]."}}],
    }
    fr_impl = AsyncMock(return_value={"count": 1, "results": [{"document_number": "2026-12345"}]})
    orchestrator = make_orchestrator(tool_llm, answer_llm, fr_impl=fr_impl)

    result = await orchestrator.handle_query("What EPA rules were proposed?", today=date(2026, 8, 13))

    assert result.answer == "EPA proposed one rule [doc:2026-12345]."
    fr_impl.assert_awaited_once_with(
        action="search", agency_slug="environmental-protection-agency",
        doc_type=None, start_date=None, end_date=None, document_number=None,
        per_page=5,
    )


@pytest.mark.asyncio
async def test_unverified_agency_match_is_flagged_in_tool_result():
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
    tool_llm = AsyncMock()
    tool_llm.chat.side_effect = [tool_call_response, NO_TOOL_CALLS_MESSAGE]
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = {"choices": [{"message": {"role": "assistant", "content": "No citable results [doc:none]."}}]}
    fr_impl = AsyncMock(return_value={"count": 0, "results": []})
    orchestrator = make_orchestrator(tool_llm, answer_llm, fr_impl=fr_impl)

    await orchestrator.handle_query("What rules did the EPA propose?", today=date(2026, 8, 13))

    second_call_messages = tool_llm.chat.call_args_list[1].args[0]
    tool_result_message = next(m for m in second_call_messages if m.get("role") == "tool")
    sent_tool_result = json.loads(tool_result_message["content"])
    assert sent_tool_result["agency_match_verified"] is False
    assert sent_tool_result["agency_match_used"] == "Environmental Protection Agency"


@pytest.mark.asyncio
async def test_uncited_claims_are_dropped_from_final_answer():
    tool_llm = AsyncMock()
    tool_llm.chat.return_value = NO_TOOL_CALLS_MESSAGE
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = {"choices": [{"message": {
        "role": "assistant",
        "content": "EPA proposed a rule [doc:2026-1]. The agency also secretly doubled its budget overnight.",
    }}]}
    orchestrator = make_orchestrator(tool_llm, answer_llm)

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
    Post-routing-split: tool_llm deciding it's done with no content is no
    longer sufficient on its own — answer_llm is always given a chance to
    synthesize from whatever was gathered, so this now also requires
    answer_llm to come back empty too.
    """
    tool_llm = AsyncMock()
    tool_llm.chat.return_value = NO_TOOL_CALLS_MESSAGE
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = NO_TOOL_CALLS_MESSAGE
    orchestrator = make_orchestrator(tool_llm, answer_llm)

    result = await orchestrator.handle_query("What is EPA?", today=date(2026, 8, 13))

    assert result.answer == ""
    assert result.needs_clarification is True
    assert result.clarification_question


@pytest.mark.asyncio
async def test_orchestrator_can_dispatch_bulk_download_actions():
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
    tool_llm = AsyncMock()
    tool_llm.chat.side_effect = [tool_call_response, NO_TOOL_CALLS_MESSAGE]
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = {"choices": [{"message": {"role": "assistant", "content": "Export started [award:job-1]."}}]}
    usaspending_impl = AsyncMock(return_value={"status": "pending", "job_id": "job-1"})
    orchestrator = make_orchestrator(tool_llm, answer_llm, usaspending_impl=usaspending_impl)

    await orchestrator.handle_query("Export all EPA awards this quarter.", today=date(2026, 8, 13))

    usaspending_impl.assert_awaited_once_with(
        action="submit_bulk_download", toptier_code="068",
        start_date="2026-01-01", end_date="2026-03-31",
        award_id=None, fiscal_year=None, job_id=None,
    )


@pytest.mark.asyncio
async def test_exhausting_tool_iteration_budget_asks_for_narrower_query():
    looping_response = {"choices": [{"message": {
        "role": "assistant",
        "tool_calls": [{
            "id": "call_x",
            "function": {"name": "search_federal_register", "arguments": json.dumps({"action": "search"})},
        }],
    }}]}
    tool_llm = AsyncMock()
    tool_llm.chat.return_value = looping_response
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = NO_TOOL_CALLS_MESSAGE
    fr_impl = AsyncMock(return_value={"count": 0, "results": []})
    orchestrator = make_orchestrator(tool_llm, answer_llm, fr_impl=fr_impl)

    result = await orchestrator.handle_query("Tell me everything about everything.", today=date(2026, 8, 13))

    assert result.needs_clarification is True
    assert "budget" in result.clarification_question
    assert tool_llm.chat.await_count == MAX_TOOL_ITERATIONS
    answer_llm.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_query_inserts_history_between_system_and_new_user_message():
    tool_llm = AsyncMock()
    tool_llm.chat.return_value = NO_TOOL_CALLS_MESSAGE
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = {"choices": [{"message": {"role": "assistant", "content": "Fine [doc:1]."}}]}
    orchestrator = make_orchestrator(tool_llm, answer_llm)
    prior_history = [
        {"role": "user", "content": "What did EPA spend last period?"},
        {"role": "assistant", "content": "EPA spent $1B [award:1]."},
    ]

    await orchestrator.handle_query(
        "Are there any newer rules?", today=date(2026, 8, 13), history=prior_history,
    )

    sent_messages = tool_llm.chat.call_args.args[0]
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[1] == prior_history[0]
    assert sent_messages[2] == prior_history[1]
    assert sent_messages[3] == {"role": "user", "content": "Are there any newer rules?"}


@pytest.mark.asyncio
async def test_truncated_search_results_get_a_deterministic_note_not_llm_prose():
    """Regression, found live 2026-08-18: chat search results are capped to
    CHAT_SEARCH_PAGE_SIZE (5) to stay under Groq's TPM limit, but a query
    like 'DOT final rules this quarter' can have hundreds of real matches
    (count=251 seen live against the actual Federal Register API). A first
    attempt asked the model to disclose the gap in its own prose, but a
    sentence about the *total* count has no single [doc:id] to cite, so
    enforce_citations silently dropped it — the disclosure never reached the
    user, it just landed in dropped_claims. The note must be generated
    deterministically from the tool result's own 'count' field so it can
    never be filtered out.
    """
    tool_call_response = {"choices": [{"message": {
        "role": "assistant",
        "tool_calls": [{
            "id": "call_1",
            "function": {"name": "search_federal_register", "arguments": json.dumps({"action": "search"})},
        }],
    }}]}
    tool_llm = AsyncMock()
    tool_llm.chat.side_effect = [tool_call_response, NO_TOOL_CALLS_MESSAGE]
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = {"choices": [{"message": {"role": "assistant", "content": "Here are a few examples [doc:1]."}}]}
    fr_impl = AsyncMock(return_value={"count": 251, "results": [{"document_number": "1"}] * 5})
    orchestrator = make_orchestrator(tool_llm, answer_llm, fr_impl=fr_impl)

    result = await orchestrator.handle_query("What final rules did DOT publish this quarter?", today=date(2026, 8, 13))

    assert "5 of 251" in result.answer
    assert "[doc:1]" in result.answer


@pytest.mark.asyncio
async def test_untruncated_search_results_get_no_note():
    tool_call_response = {"choices": [{"message": {
        "role": "assistant",
        "tool_calls": [{
            "id": "call_1",
            "function": {"name": "search_federal_register", "arguments": json.dumps({"action": "search"})},
        }],
    }}]}
    tool_llm = AsyncMock()
    tool_llm.chat.side_effect = [tool_call_response, NO_TOOL_CALLS_MESSAGE]
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = {"choices": [{"message": {"role": "assistant", "content": "Just this one [doc:1]."}}]}
    fr_impl = AsyncMock(return_value={"count": 1, "results": [{"document_number": "1"}]})
    orchestrator = make_orchestrator(tool_llm, answer_llm, fr_impl=fr_impl)

    result = await orchestrator.handle_query("What final rule did DOT publish this quarter?", today=date(2026, 8, 13))

    assert "of" not in result.answer.lower().replace("just this one", "")
    assert result.answer.strip() == "Just this one [doc:1]."


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
    tool_llm = AsyncMock()
    tool_llm.chat.side_effect = [tool_call_response, NO_TOOL_CALLS_MESSAGE]
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "EPA proposed one rule [doc:2026-12345]."}}],
    }
    fr_impl = AsyncMock(return_value={"count": 1, "results": [{"document_number": "2026-12345"}]})
    orchestrator = make_orchestrator(tool_llm, answer_llm, fr_impl=fr_impl)

    await orchestrator.handle_query("What is EPA?", today=date(2026, 8, 13))

    second_call_messages = tool_llm.chat.call_args_list[1].args[0]
    assistant_message = next(m for m in second_call_messages if m.get("role") == "assistant")
    assert "reasoning" not in assistant_message
    assert "reasoning_details" not in assistant_message
    assert assistant_message["tool_calls"] == tool_call_response["choices"][0]["message"]["tool_calls"]


@pytest.mark.asyncio
async def test_final_answer_is_synthesized_by_answer_llm_not_tool_llm():
    """Core behavior of the tool_llm/answer_llm split: whatever content the
    small tool-selection model produces when it stops calling tools is
    discarded — the actual final answer always comes from one dedicated
    answer_llm call, made without tools so the model has no choice but to
    respond with content.
    """
    tool_llm = AsyncMock()
    tool_llm.chat.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "small model's own draft — should be discarded"}}],
    }
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "EPA spent $1B [award:1]."}}],
    }
    orchestrator = make_orchestrator(tool_llm, answer_llm)

    result = await orchestrator.handle_query("What did EPA spend?", today=date(2026, 8, 13))

    assert result.answer == "EPA spent $1B [award:1]."
    answer_llm.chat.assert_awaited_once_with(
        tool_llm.chat.call_args.args[0], tools=None,
    )


@pytest.mark.asyncio
async def test_answer_llm_call_is_told_not_to_call_more_tools():
    """Regression: Groq rejects `chat(messages, tools=None)` with a 400
    ("Tool choice is none, but model called a tool") whenever the model
    still tries to emit a tool call despite no tools being declared on that
    request — which it reliably does here, since the system prompt tells it
    to always use tools to look up facts, and this call follows right after
    a conversation full of tool calls. Passing tool_choice="none" instead of
    omitting tools does NOT fix this live (verified 2026-08-19) — Groq still
    errors if the model attempts a call at all, regardless of tool_choice.
    The fix that verified working live is an explicit instruction message
    telling the model not to call any more tools and to answer now; this
    test locks that in without needing a real Groq call.
    """
    tool_llm = AsyncMock()
    tool_llm.chat.return_value = NO_TOOL_CALLS_MESSAGE
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "EPA spent $1B [award:1]."}}],
    }
    orchestrator = make_orchestrator(tool_llm, answer_llm)

    await orchestrator.handle_query("What did EPA spend?", today=date(2026, 8, 13))

    sent_messages = answer_llm.chat.call_args.args[0]
    assert sent_messages[-1]["role"] == "user"
    assert "do not call any more tools" in sent_messages[-1]["content"].lower()


@pytest.mark.asyncio
async def test_stream_yields_status_before_tool_dispatch_and_final_answer_event():
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
    tool_llm = AsyncMock()
    tool_llm.chat.side_effect = [tool_call_response, NO_TOOL_CALLS_MESSAGE]
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "EPA proposed one rule [doc:2026-12345]."}}],
    }
    fr_impl = AsyncMock(return_value={"count": 1, "results": [{"document_number": "2026-12345"}]})
    orchestrator = make_orchestrator(tool_llm, answer_llm, fr_impl=fr_impl)

    events = [
        event async for event in orchestrator.handle_query_stream(
            "What EPA rules were proposed?", today=date(2026, 8, 13),
        )
    ]

    assert events[0] == {
        "type": "status", "tool": "search_federal_register", "message": "Searching Federal Register…",
    }
    assert {"type": "status", "tool": "synthesize_answer", "message": "Writing your answer…"} in events
    assert events[-1] == {
        "type": "answer", "answer": "EPA proposed one rule [doc:2026-12345].",
        "dropped_claims": [], "needs_clarification": False, "clarification_question": None,
    }


@pytest.mark.asyncio
async def test_stream_emits_one_status_event_per_concurrent_tool_call_plus_synthesis():
    tool_call_response = {
        "choices": [{"message": {
            "role": "assistant",
            "tool_calls": [
                {"id": "call_1", "function": {
                    "name": "search_federal_register",
                    "arguments": json.dumps({"action": "search", "agency_name": "Environmental Protection Agency"}),
                }},
                {"id": "call_2", "function": {
                    "name": "query_usaspending",
                    "arguments": json.dumps({"action": "spending_by_agency", "agency_name": "Environmental Protection Agency"}),
                }},
            ],
        }}],
    }
    tool_llm = AsyncMock()
    tool_llm.chat.side_effect = [tool_call_response, NO_TOOL_CALLS_MESSAGE]
    answer_llm = AsyncMock()
    answer_llm.chat.return_value = {"choices": [{"message": {"role": "assistant", "content": "Summary [doc:1]."}}]}
    fr_impl = AsyncMock(return_value={"count": 1, "results": [{"document_number": "1"}]})
    usaspending_impl = AsyncMock(return_value={"amount": 100})
    orchestrator = make_orchestrator(tool_llm, answer_llm, fr_impl=fr_impl, usaspending_impl=usaspending_impl)

    events = [
        event async for event in orchestrator.handle_query_stream(
            "What did EPA do?", today=date(2026, 8, 13),
        )
    ]

    status_events = [e for e in events if e["type"] == "status"]
    assert [e["tool"] for e in status_events] == ["search_federal_register", "query_usaspending", "synthesize_answer"]


@pytest.mark.asyncio
async def test_stream_ambiguous_period_yields_only_clarification_answer_event():
    tool_llm = AsyncMock()
    answer_llm = AsyncMock()
    orchestrator = make_orchestrator(tool_llm, answer_llm)

    events = [
        event async for event in orchestrator.handle_query_stream(
            "What did EPA spend this year?", today=date(2026, 8, 13),
        )
    ]

    assert len(events) == 1
    assert events[0]["type"] == "answer"
    assert events[0]["needs_clarification"] is True
    tool_llm.chat.assert_not_awaited()
    answer_llm.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_propagates_tool_llm_errors_instead_of_swallowing_them():
    tool_llm = AsyncMock()
    tool_llm.chat.side_effect = httpx.HTTPStatusError(
        "429", request=httpx.Request("POST", "http://x"), response=httpx.Response(429),
    )
    answer_llm = AsyncMock()
    orchestrator = make_orchestrator(tool_llm, answer_llm)

    with pytest.raises(httpx.HTTPStatusError):
        async for _ in orchestrator.handle_query_stream("What is EPA?", today=date(2026, 8, 13)):
            pass


@pytest.mark.asyncio
async def test_stream_propagates_answer_llm_errors_instead_of_swallowing_them():
    tool_llm = AsyncMock()
    tool_llm.chat.return_value = NO_TOOL_CALLS_MESSAGE
    answer_llm = AsyncMock()
    answer_llm.chat.side_effect = httpx.HTTPStatusError(
        "429", request=httpx.Request("POST", "http://x"), response=httpx.Response(429),
    )
    orchestrator = make_orchestrator(tool_llm, answer_llm)

    with pytest.raises(httpx.HTTPStatusError):
        async for _ in orchestrator.handle_query_stream("What is EPA?", today=date(2026, 8, 13)):
            pass
