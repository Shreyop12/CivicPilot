import json
import logging
from dataclasses import dataclass, field
from datetime import date

from ..crosswalk import AgencyCrosswalk
from ..date_resolver import DateResolver
from .citation_guard import enforce_citations
from .llm_client import GroqClient

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5

SYSTEM_PROMPT_TEMPLATE = (
    "You are CivicPilot, an assistant that answers questions about US federal "
    "rules and related government spending. Always call the provided tools to "
    "look up facts rather than relying on prior knowledge. When you give your "
    "final answer, cite every factual claim with the source's own identifier "
    "in ASCII square brackets — always the plain characters [ and ], never "
    "full-width or any other bracket style. Use [doc:2026-12345] for a "
    "Federal Register document, [award:AWD-1] for a specific USAspending "
    "award record, or [award:<toptier_code>-FY<year>] (e.g. [award:068-FY2026]) "
    "for an agency-wide spending_by_agency total for that fiscal year — there "
    "is no award ID for an aggregate total, so use the agency's toptier code "
    "and fiscal year instead. Never state a fact you cannot cite this way. "
    "Today's date is {today}. Federal Register uses calendar dates; "
    "USAspending fiscal years run October 1 to September 30. Never guess a "
    "date range — derive it from today's date. If a tool result includes "
    "\"agency_match_verified\": false, you must state in your final answer "
    "which agency name was actually matched rather than silently trusting it."
)

FR_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_federal_register",
        "description": "Search or fetch Federal Register documents (proposed/final rules).",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["search", "get"]},
                "agency_name": {
                    "type": "string",
                    "description": "Plain-language agency name, e.g. 'Environmental Protection Agency'",
                },
                "doc_type": {"type": "string", "enum": ["RULE", "PRORULE"]},
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "document_number": {"type": "string"},
            },
            "required": ["action"],
        },
    },
}

USASPENDING_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "query_usaspending",
        "description": "Query USAspending award/spending data for a federal agency.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "search_awards", "get_award", "spending_by_agency",
                        "submit_bulk_download", "get_bulk_download_result",
                    ],
                },
                "agency_name": {"type": "string", "description": "Plain-language agency name"},
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "award_id": {"type": "string"},
                "fiscal_year": {"type": "integer"},
                "job_id": {"type": "string", "description": "Returned by a prior submit_bulk_download call"},
            },
            "required": ["action"],
        },
    },
}


@dataclass
class OrchestratorResult:
    answer: str
    dropped_claims: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None


class Orchestrator:
    def __init__(
        self,
        llm: GroqClient,
        fr_impl,
        usaspending_impl,
        crosswalk: AgencyCrosswalk,
        date_resolver: DateResolver,
    ):
        self._llm = llm
        self._fr_impl = fr_impl
        self._usaspending_impl = usaspending_impl
        self._crosswalk = crosswalk
        self._date_resolver = date_resolver

    def _detect_ambiguous_period(self, query: str, today: date):
        lowered = query.lower()
        for phrase, period in (
            ("this quarter", "quarter"), ("this year", "year"),
        ):
            if phrase in lowered:
                resolution = self._date_resolver.resolve(period, today)
                return phrase, resolution
        return None

    async def _dispatch_tool_call(self, name: str, arguments: dict) -> dict:
        agency_name = arguments.get("agency_name")
        resolution = self._crosswalk.resolve(agency_name) if agency_name else None

        if agency_name and resolution is not None:
            if name == "search_federal_register" and resolution.fr_slug is None:
                return {
                    "error": (
                        f"Could not resolve agency {agency_name!r} to a known agency; "
                        "ask the user to confirm the official agency name."
                    ),
                }
            if name == "query_usaspending" and resolution.usaspending_toptier_code is None:
                return {
                    "error": (
                        f"Could not resolve agency {agency_name!r} to a known agency; "
                        "ask the user to confirm the official agency name."
                    ),
                }

        if name == "search_federal_register":
            result = await self._fr_impl(
                action=arguments["action"],
                agency_slug=resolution.fr_slug if resolution else None,
                doc_type=arguments.get("doc_type"),
                start_date=arguments.get("start_date"),
                end_date=arguments.get("end_date"),
                document_number=arguments.get("document_number"),
            )
        elif name == "query_usaspending":
            result = await self._usaspending_impl(
                action=arguments["action"],
                toptier_code=resolution.usaspending_toptier_code if resolution else None,
                start_date=arguments.get("start_date"),
                end_date=arguments.get("end_date"),
                award_id=arguments.get("award_id"),
                fiscal_year=arguments.get("fiscal_year"),
                job_id=arguments.get("job_id"),
            )
        else:
            raise ValueError(f"unknown tool: {name!r}")

        if resolution is not None and not resolution.verified:
            result = {**result, "agency_match_verified": False, "agency_match_used": resolution.matched_name}
        return result

    async def handle_query(
        self, user_query: str, today: date | None = None, history: list[dict] | None = None,
    ) -> OrchestratorResult:
        today = today or date.today()

        ambiguity = self._detect_ambiguous_period(user_query, today)
        resolved_addendum = None
        if ambiguity is not None:
            phrase, resolution = ambiguity
            if resolution.diverges:
                return OrchestratorResult(
                    answer="",
                    needs_clarification=True,
                    clarification_question=(
                        f"You said '{phrase}' — do you mean the calendar {resolution.period_label} "
                        f"({resolution.calendar_range.start} to {resolution.calendar_range.end}) or the "
                        f"federal fiscal {resolution.period_label} "
                        f"({resolution.fiscal_range.start} to {resolution.fiscal_range.end})?"
                    ),
                )
            resolved_addendum = (
                f"The user said '{phrase}', which resolves to {resolution.calendar_range.start} "
                f"through {resolution.calendar_range.end} — mention this range in your answer."
            )

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(today=today.isoformat())
        if resolved_addendum:
            system_prompt = f"{system_prompt} {resolved_addendum}"

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_query})
        tools = [FR_TOOL_SCHEMA, USASPENDING_TOOL_SCHEMA]

        for _ in range(MAX_TOOL_ITERATIONS):
            response = await self._llm.chat(messages, tools=tools)
            message = response["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                raw_answer = message.get("content") or ""
                filtered_answer, dropped = enforce_citations(raw_answer)
                return OrchestratorResult(answer=filtered_answer, dropped_claims=dropped)

            # Some models (e.g. gpt-oss on Groq) attach a verbose reasoning
            # trace to the raw message. Only the chat-completions API
            # contract fields belong in history — carrying the trace forward
            # on every subsequent iteration compounds token usage fast
            # enough to blow a low TPM limit on an ordinary multi-tool query.
            messages.append({"role": message["role"], "content": message.get("content"), "tool_calls": tool_calls})
            for call in tool_calls:
                try:
                    fn = call["function"]
                    arguments = json.loads(fn["arguments"])
                    result = await self._dispatch_tool_call(fn["name"], arguments)
                    content = json.dumps(result)
                except Exception as exc:
                    tool_name = call.get("function", {}).get("name", "<unknown>")
                    logger.exception("Tool dispatch failed for tool %r", tool_name)
                    content = json.dumps({"error": str(exc)})
                messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": content})

        # Tool-call budget exhausted. Give the model one last chance to answer
        # from whatever it already gathered, instead of discarding it outright.
        final_response = await self._llm.chat(messages, tools=None)
        final_message = final_response["choices"][0]["message"]
        raw_answer = final_message.get("content") or ""
        filtered_answer, dropped = enforce_citations(raw_answer)
        if filtered_answer.strip():
            return OrchestratorResult(answer=filtered_answer, dropped_claims=dropped)

        return OrchestratorResult(
            answer="",
            needs_clarification=True,
            clarification_question=(
                "I couldn't complete this query within the available tool-call budget "
                "— could you narrow it down?"
            ),
        )
