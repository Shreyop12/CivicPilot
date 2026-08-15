# CivicPilot Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an agency dashboard (spending chart + recent rules) with a persistent grounded-chat panel to CivicPilot, backed by a new FastAPI layer that wraps the existing orchestrator/clients without modifying their core behavior.

**Architecture:** A new `civicpilot/api/` FastAPI package exposes REST endpoints over the existing `Orchestrator`, `FederalRegisterClient`, and `USASpendingClient` — the dashboard endpoint calls the tool impls directly (no LLM, no tokens spent), the chat endpoint wraps `Orchestrator.handle_query`. A new `frontend/` React SPA (Vite + Tailwind + hand-authored shadcn-style components) consumes that API. Multi-turn chat memory is compact Q&A-pair replay, not raw tool-trace replay, to avoid reintroducing the token-budget problem fixed earlier the same day.

**Tech Stack:** FastAPI + uvicorn (backend API), React 18 + TypeScript + Vite + Tailwind CSS v3 (frontend), Recharts (chart), Vitest + React Testing Library (frontend tests), pytest + httpx ASGITransport (backend API tests).

**Spec:** [docs/superpowers/specs/2026-08-14-civicpilot-frontend-design.md](../specs/2026-08-14-civicpilot-frontend-design.md)

## Global Constraints

- Python `>=3.11` (existing `pyproject.toml` floor) — new backend code must run under it.
- `httpx>=0.27` already required; API tests use `httpx.ASGITransport`, available from that floor.
- No database — conversation history is in-memory only (`dict` on `app.state`), lost on restart.
- No auth / multi-user accounts — single-instance, local-only v1.
- Dashboard shows **final rules only** (`doc_type="RULE"`), last 12 months — no proposed rules (PRORULE).
- Spending chart shows **last 3 fiscal years**; the current (in-progress) fiscal year is visually marked `partial: true`.
- `[doc:...]` citation stamps link to the source's `html_url`; `[award:...]` stamps from `spending_by_agency` are never clickable (that endpoint has no per-award URL).
- Existing modules (`civicpilot/agent/*`, `civicpilot/clients/*`, `civicpilot/servers/*`, `crosswalk.py`, `date_resolver.py`) are unchanged except: `AgencyCrosswalk.list_all()` (new method), `Orchestrator.handle_query(..., history=...)` (new optional param), and `civicpilot/main.py`'s `build_orchestrator()` returning a new `AppComponents` dataclass instead of a bare tuple.
- Frontend build must produce a real production build (`npm run build`) even though it isn't deployed as part of this work — matches "needs to be deployable/shareable" from the spec.

---

## Task 1: `AgencyCrosswalk.list_all()`

**Files:**
- Modify: `civicpilot/crosswalk.py`
- Test: `tests/test_crosswalk.py`

**Interfaces:**
- Produces: `AgencyCrosswalk.list_all() -> list[AgencyMapping]` — used by Task 5 (agencies endpoint) and Task 6 (dashboard endpoint) to enumerate/look up agencies without a new fuzzy-search endpoint.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_crosswalk.py`:

```python
def test_list_all_returns_every_mapping():
    crosswalk = AgencyCrosswalk([
        AgencyMapping("Environmental Protection Agency", "environmental-protection-agency", "068"),
        AgencyMapping("Department of Energy", "energy-department", "089"),
    ])

    result = crosswalk.list_all()

    assert {m.name for m in result} == {"Environmental Protection Agency", "Department of Energy"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosswalk.py::test_list_all_returns_every_mapping -v`
Expected: FAIL with `AttributeError: 'AgencyCrosswalk' object has no attribute 'list_all'`

- [ ] **Step 3: Implement**

In `civicpilot/crosswalk.py`, add a method to `AgencyCrosswalk` (after `resolve`):

```python
    def list_all(self) -> list[AgencyMapping]:
        return list(self._by_name.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosswalk.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add civicpilot/crosswalk.py tests/test_crosswalk.py
git commit -m "feat: add AgencyCrosswalk.list_all() for agency-listing endpoints"
```

---

## Task 2: `build_orchestrator()` returns `AppComponents`

**Why:** The dashboard endpoint (Task 6) needs direct access to `fr_impl`/`usaspending_impl`/`crosswalk`, not just the `Orchestrator`. Rather than duplicate the wiring logic in `civicpilot/api/`, `build_orchestrator()` returns a small bundle both the CLI and the API layer share.

**Files:**
- Modify: `civicpilot/main.py`
- Modify: `tests/test_main.py`

**Interfaces:**
- Produces: `AppComponents` dataclass with fields `orchestrator: Orchestrator`, `http: httpx.AsyncClient`, `fr_impl: Callable[..., Awaitable[dict]]`, `usaspending_impl: Callable[..., Awaitable[dict]]`, `crosswalk: AgencyCrosswalk`. `build_orchestrator() -> AppComponents` (was `-> tuple[Orchestrator, httpx.AsyncClient]`). Used by Task 4's FastAPI lifespan and by every route depending on `get_components`.

- [ ] **Step 1: Update the failing tests first**

Replace the three tests in `tests/test_main.py` with:

```python
import httpx
import pytest

from civicpilot.agent.llm_client import FailoverLLMClient, GroqClient
from civicpilot.agent.orchestrator import Orchestrator
from civicpilot.crosswalk import AgencyCrosswalk
from civicpilot.main import build_orchestrator


@pytest.mark.asyncio
async def test_build_orchestrator_wires_all_components(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("civicpilot.main.load_dotenv", lambda *args, **kwargs: None)
    components = await build_orchestrator()
    try:
        assert isinstance(components.orchestrator, Orchestrator)
        assert isinstance(components.http, httpx.AsyncClient)
        assert isinstance(components.orchestrator._llm, GroqClient)
        assert isinstance(components.crosswalk, AgencyCrosswalk)
        assert callable(components.fr_impl)
        assert callable(components.usaspending_impl)
    finally:
        await components.http.aclose()


@pytest.mark.asyncio
async def test_build_orchestrator_wires_failover_llm_when_openrouter_key_present(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setattr("civicpilot.main.load_dotenv", lambda *args, **kwargs: None)
    components = await build_orchestrator()
    try:
        assert isinstance(components.orchestrator._llm, FailoverLLMClient)
    finally:
        await components.http.aclose()


@pytest.mark.asyncio
async def test_build_orchestrator_raises_systemexit_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr("civicpilot.main.load_dotenv", lambda *args, **kwargs: None)
    with pytest.raises(SystemExit):
        await build_orchestrator()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — `build_orchestrator()` still returns a tuple, so `components.orchestrator` raises `AttributeError`.

- [ ] **Step 3: Implement**

Replace the full contents of `civicpilot/main.py`:

```python
import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv

from .agent.llm_client import FailoverLLMClient, GroqClient, OpenRouterClient
from .agent.orchestrator import Orchestrator
from .cache import QueryCache
from .clients.fr_client import FederalRegisterClient
from .clients.usaspending_client import USASpendingClient
from .clients.usaspending_download_client import USASpendingDownloadClient
from .crosswalk import AgencyCrosswalk, load_default_crosswalk
from .date_resolver import DateResolver
from .servers.fr_server import build_fr_server
from .servers.usaspending_server import build_usaspending_server


@dataclass
class AppComponents:
    orchestrator: Orchestrator
    http: httpx.AsyncClient
    fr_impl: Callable[..., Awaitable[dict]]
    usaspending_impl: Callable[..., Awaitable[dict]]
    crosswalk: AgencyCrosswalk


async def build_orchestrator() -> AppComponents:
    load_dotenv()
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY environment variable is not set")
        raise SystemExit(1)

    http = httpx.AsyncClient(timeout=30.0)
    cache = QueryCache()

    fr_server = build_fr_server(FederalRegisterClient(http, cache))
    usaspending_server = build_usaspending_server(
        USASpendingClient(http, cache), USASpendingDownloadClient(http),
    )

    primary_llm = GroqClient(http, api_key=api_key)
    fallback_api_key = os.environ.get("OPENROUTER_API_KEY")
    if fallback_api_key:
        llm = FailoverLLMClient(primary_llm, OpenRouterClient(http, api_key=fallback_api_key))
    else:
        logging.getLogger(__name__).warning(
            "OPENROUTER_API_KEY not set — no fallback LLM configured; a Groq "
            "outage or rate limit will fail the whole query."
        )
        llm = primary_llm

    crosswalk = load_default_crosswalk()
    orchestrator = Orchestrator(
        llm=llm,
        fr_impl=fr_server._search_documents_impl,
        usaspending_impl=usaspending_server._query_spending_impl,
        crosswalk=crosswalk,
        date_resolver=DateResolver(),
    )
    return AppComponents(
        orchestrator=orchestrator,
        http=http,
        fr_impl=fr_server._search_documents_impl,
        usaspending_impl=usaspending_server._query_spending_impl,
        crosswalk=crosswalk,
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    components = await build_orchestrator()
    try:
        query = input("Ask CivicPilot: ")
        result = await components.orchestrator.handle_query(query)
        if result.needs_clarification:
            print(result.clarification_question)
        else:
            print(result.answer)
    finally:
        await components.http.aclose()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full suite to check for regressions**

Run: `pytest tests/ -v`
Expected: all PASS (no other file references the old tuple return)

- [ ] **Step 6: Commit**

```bash
git add civicpilot/main.py tests/test_main.py
git commit -m "refactor: build_orchestrator() returns AppComponents bundle

Needed so the new API layer can reuse fr_impl/usaspending_impl/crosswalk
directly for the dashboard endpoint without duplicating wiring logic."
```

---

## Task 3: `Orchestrator.handle_query` accepts compact conversation history

**Files:**
- Modify: `civicpilot/agent/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Orchestrator.handle_query(user_query: str, today: date | None = None, history: list[dict] | None = None) -> OrchestratorResult`. `history` entries are `{"role": "user"|"assistant", "content": str}` — prior *answers*, never raw tool-call/tool-result messages. Used by Task 7 (chat endpoint).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_orchestrator.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orchestrator.py::test_handle_query_inserts_history_between_system_and_new_user_message -v`
Expected: FAIL with `TypeError: handle_query() got an unexpected keyword argument 'history'`

- [ ] **Step 3: Implement**

In `civicpilot/agent/orchestrator.py`, change the `handle_query` signature and message construction:

```python
    async def handle_query(
        self, user_query: str, today: date | None = None, history: list[dict] | None = None,
    ) -> OrchestratorResult:
```

Replace:

```python
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ]
```

with:

```python
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_query})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_orchestrator.py -v`
Expected: all PASS (existing tests pass `history=None` implicitly, `if history:` skips the empty case)

- [ ] **Step 5: Commit**

```bash
git add civicpilot/agent/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: Orchestrator.handle_query accepts prior Q&A history

History is compact {role, content} pairs of past questions and final
answers only — never raw tool-call/tool-result messages — so replaying
it across turns doesn't reintroduce the token-budget pressure a single
tool result can already cause."
```

---

## Task 4: FastAPI app scaffold + health check

**Files:**
- Create: `civicpilot/api/__init__.py`
- Create: `civicpilot/api/deps.py`
- Create: `civicpilot/api/app.py`
- Create: `tests/api/__init__.py`
- Create: `tests/api/test_app.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `civicpilot.api.deps.get_components(request) -> AppComponents`, `civicpilot.api.deps.get_conversations(request) -> dict`, `civicpilot.api.app.create_app() -> FastAPI`, module-level `civicpilot.api.app.app`. Used by every subsequent route task.

- [ ] **Step 1: Add backend dependencies**

In `pyproject.toml`, add to `dependencies`:

```toml
dependencies = [
    "httpx>=0.27",
    "mcp>=1.0,<2.0",
    "rapidfuzz>=3.9",
    "python-dotenv>=1.0",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
]
```

Run: `pip install -e ".[dev]"` (dev extras already include pytest/pytest-asyncio/respx; the new core deps install with the base package)

- [ ] **Step 2: Write the failing test**

Create `tests/api/__init__.py` (empty file).

Create `tests/api/test_app.py`:

```python
import httpx
import pytest

from civicpilot.api.app import create_app


@pytest.mark.asyncio
async def test_health_check_returns_ok():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/api/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'civicpilot.api'`

- [ ] **Step 4: Implement**

Create `civicpilot/api/__init__.py` (empty file).

Create `civicpilot/api/deps.py`:

```python
from fastapi import Request

from ..main import AppComponents


def get_components(request: Request) -> AppComponents:
    return request.app.state.components


def get_conversations(request: Request) -> dict:
    return request.app.state.conversations
```

Create `civicpilot/api/app.py`:

```python
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..main import build_orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    components = await build_orchestrator()
    app.state.components = components
    app.state.conversations = {}
    try:
        yield
    finally:
        await components.http.aclose()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    cors_origin = os.environ.get("CORS_ORIGIN", "http://localhost:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cors_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
```

Note: `httpx.ASGITransport` does not trigger FastAPI's `lifespan` context, so `test_health_check_returns_ok` never touches `app.state.components` — this is intentional and is why the health check doesn't depend on real components. Later route tests (Tasks 5-7) set `app.state`/override dependencies directly instead of relying on lifespan.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/api/test_app.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add civicpilot/api/__init__.py civicpilot/api/deps.py civicpilot/api/app.py tests/api/__init__.py tests/api/test_app.py pyproject.toml
git commit -m "feat: scaffold FastAPI app with health check"
```

---

## Task 5: `GET /api/agencies`

**Files:**
- Create: `civicpilot/api/schemas.py`
- Create: `civicpilot/api/routes/__init__.py`
- Create: `civicpilot/api/routes/agencies.py`
- Modify: `civicpilot/api/app.py`
- Create: `tests/api/test_agencies_routes.py`

**Interfaces:**
- Consumes: `AgencyCrosswalk.list_all()` (Task 1), `get_components` (Task 4).
- Produces: `civicpilot.api.schemas.AgencySummary` (fields: `name: str`, `toptier_code: str`, `fr_slug: str | None`), `GET /api/agencies` route. `civicpilot.api.routes.agencies.router` (an `APIRouter`) — also extended in Task 6.

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_agencies_routes.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_agencies_routes.py -v`
Expected: FAIL — `404 Not Found` (route doesn't exist yet) or `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Create `civicpilot/api/schemas.py`:

```python
from pydantic import BaseModel


class AgencySummary(BaseModel):
    name: str
    toptier_code: str
    fr_slug: str | None


class ObligationYear(BaseModel):
    fiscal_year: int
    amount: float
    partial: bool


class RuleSummary(BaseModel):
    document_number: str
    title: str
    type: str
    publication_date: str
    html_url: str


class AgencyDashboard(BaseModel):
    name: str
    toptier_code: str
    fr_slug: str | None
    obligations: list[ObligationYear]
    rules: list[RuleSummary]


class ChatRequest(BaseModel):
    conversation_id: str
    message: str


class ChatResponse(BaseModel):
    answer: str
    dropped_claims: list[str]
    needs_clarification: bool
    clarification_question: str | None
```

Create `civicpilot/api/routes/__init__.py` (empty file).

Create `civicpilot/api/routes/agencies.py`:

```python
from fastapi import APIRouter, Depends

from ..deps import get_components
from ..schemas import AgencySummary
from ...main import AppComponents

router = APIRouter()


@router.get("/agencies", response_model=list[AgencySummary])
async def list_agencies(components: AppComponents = Depends(get_components)) -> list[AgencySummary]:
    return [
        AgencySummary(name=m.name, toptier_code=m.usaspending_toptier_code, fr_slug=m.fr_slug)
        for m in components.crosswalk.list_all()
    ]
```

In `civicpilot/api/app.py`, add the import and router registration:

```python
from .routes.agencies import router as agencies_router
```

and, inside `create_app()`, after the `/api/health` route definition:

```python
    app.include_router(agencies_router, prefix="/api")

    return app
```

(Move the existing `return app` down to after this line.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_agencies_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add civicpilot/api/schemas.py civicpilot/api/routes/__init__.py civicpilot/api/routes/agencies.py civicpilot/api/app.py tests/api/test_agencies_routes.py
git commit -m "feat: add GET /api/agencies endpoint"
```

---

## Task 6: `GET /api/agencies/{toptier_code}/dashboard`

**Files:**
- Modify: `civicpilot/api/routes/agencies.py`
- Modify: `tests/api/test_agencies_routes.py`

**Interfaces:**
- Consumes: `components.usaspending_impl(action="spending_by_agency", toptier_code=..., fiscal_year=...)`, `components.fr_impl(action="search", agency_slug=..., doc_type="RULE", start_date=..., end_date=...)` (both from Task 2's `AppComponents`).
- Produces: `build_dashboard(components, toptier_code, today=None) -> AgencyDashboard` (testable helper, mirrors the codebase's existing `_search_documents_impl`/`_query_spending_impl` pattern of separating the testable implementation from the thin route). `GET /api/agencies/{toptier_code}/dashboard` route, 404 on unknown `toptier_code`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/api/test_agencies_routes.py`:

```python
from datetime import date

from civicpilot.api.routes.agencies import build_dashboard


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_agencies_routes.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_dashboard'`

- [ ] **Step 3: Implement**

Replace the full contents of `civicpilot/api/routes/agencies.py`:

```python
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_components
from ..schemas import AgencyDashboard, AgencySummary, ObligationYear, RuleSummary
from ...main import AppComponents

router = APIRouter()


def _current_fiscal_year(today: date) -> int:
    return today.year + 1 if today.month >= 10 else today.year


async def build_dashboard(
    components: AppComponents, toptier_code: str, today: date | None = None,
) -> AgencyDashboard:
    today = today or date.today()
    mapping = next(
        (m for m in components.crosswalk.list_all() if m.usaspending_toptier_code == toptier_code),
        None,
    )
    if mapping is None:
        raise HTTPException(status_code=404, detail=f"unknown toptier_code: {toptier_code!r}")

    current_fy = _current_fiscal_year(today)
    fiscal_years = [current_fy - 2, current_fy - 1, current_fy]
    obligations = []
    for fiscal_year in fiscal_years:
        result = await components.usaspending_impl(
            action="spending_by_agency", toptier_code=toptier_code, fiscal_year=fiscal_year,
        )
        obligations.append(
            ObligationYear(
                fiscal_year=fiscal_year,
                amount=result["obligations"],
                partial=(fiscal_year == current_fy),
            )
        )

    start_date = (today - timedelta(days=365)).isoformat()
    fr_result = await components.fr_impl(
        action="search", agency_slug=mapping.fr_slug, doc_type="RULE",
        start_date=start_date, end_date=today.isoformat(),
    )
    rules = [
        RuleSummary(
            document_number=doc["document_number"],
            title=doc["title"],
            type=doc["type"],
            publication_date=doc["publication_date"],
            html_url=doc["html_url"],
        )
        for doc in fr_result.get("results", [])
    ]

    return AgencyDashboard(
        name=mapping.name,
        toptier_code=mapping.usaspending_toptier_code,
        fr_slug=mapping.fr_slug,
        obligations=obligations,
        rules=rules,
    )


@router.get("/agencies", response_model=list[AgencySummary])
async def list_agencies(components: AppComponents = Depends(get_components)) -> list[AgencySummary]:
    return [
        AgencySummary(name=m.name, toptier_code=m.usaspending_toptier_code, fr_slug=m.fr_slug)
        for m in components.crosswalk.list_all()
    ]


@router.get("/agencies/{toptier_code}/dashboard", response_model=AgencyDashboard)
async def get_dashboard(
    toptier_code: str, components: AppComponents = Depends(get_components),
) -> AgencyDashboard:
    return await build_dashboard(components, toptier_code)
```

Add the corresponding imports at the top of `tests/api/test_agencies_routes.py` (`from datetime import date`, `from civicpilot.api.routes.agencies import build_dashboard`, and the existing `create_app`/`get_components`/`httpx`/`pytest` imports already present from Task 5).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_agencies_routes.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add civicpilot/api/routes/agencies.py tests/api/test_agencies_routes.py
git commit -m "feat: add GET /api/agencies/{toptier_code}/dashboard endpoint

Calls fr_impl/usaspending_impl directly, bypassing the LLM entirely —
this is data the app already has, not something to ask a model to
fetch."
```

---

## Task 7: `POST /api/chat`

**Files:**
- Create: `civicpilot/api/routes/chat.py`
- Modify: `civicpilot/api/app.py`
- Create: `tests/api/test_chat_routes.py`

**Interfaces:**
- Consumes: `Orchestrator.handle_query(message, history=...)` (Task 3), `get_components`/`get_conversations` (Task 4).
- Produces: `POST /api/chat` route. `civicpilot.api.schemas.ChatRequest`/`ChatResponse` (already defined in Task 5).

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_chat_routes.py`:

```python
from unittest.mock import AsyncMock

import httpx
import pytest

from civicpilot.agent.orchestrator import OrchestratorResult
from civicpilot.api.app import create_app
from civicpilot.api.deps import get_components, get_conversations


def make_fake_components(handle_query_result):
    class FakeComponents:
        orchestrator = AsyncMock()
        fr_impl = AsyncMock()
        usaspending_impl = AsyncMock()
        crosswalk = None

    components = FakeComponents()
    components.orchestrator.handle_query = AsyncMock(return_value=handle_query_result)
    return components


@pytest.mark.asyncio
async def test_chat_returns_answer_and_stores_compact_history():
    result = OrchestratorResult(answer="EPA spent $1B [award:1].", dropped_claims=["unsupported claim"])
    components = make_fake_components(result)
    conversations: dict = {}

    app = create_app()
    app.dependency_overrides[get_components] = lambda: components
    app.dependency_overrides[get_conversations] = lambda: conversations

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat", json={"conversation_id": "conv-1", "message": "What did EPA spend?"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "EPA spent $1B [award:1]."
    assert body["dropped_claims"] == ["unsupported claim"]
    assert body["needs_clarification"] is False

    assert conversations["conv-1"] == [
        {"role": "user", "content": "What did EPA spend?"},
        {"role": "assistant", "content": "EPA spent $1B [award:1]."},
    ]
    components.orchestrator.handle_query.assert_awaited_once_with("What did EPA spend?", history=[])


@pytest.mark.asyncio
async def test_chat_passes_prior_history_and_appends_clarification_as_assistant_turn():
    result = OrchestratorResult(
        answer="", needs_clarification=True, clarification_question="Calendar or fiscal year?",
    )
    components = make_fake_components(result)
    prior = [{"role": "user", "content": "What did EPA spend this year?"}]
    conversations = {"conv-2": prior}

    app = create_app()
    app.dependency_overrides[get_components] = lambda: components
    app.dependency_overrides[get_conversations] = lambda: conversations

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat", json={"conversation_id": "conv-2", "message": "This year"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["needs_clarification"] is True
    assert body["clarification_question"] == "Calendar or fiscal year?"

    components.orchestrator.handle_query.assert_awaited_once_with("This year", history=prior)
    assert conversations["conv-2"][-1] == {"role": "assistant", "content": "Calendar or fiscal year?"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_chat_routes.py -v`
Expected: FAIL — `404 Not Found` (route doesn't exist yet)

- [ ] **Step 3: Implement**

Create `civicpilot/api/routes/chat.py`:

```python
from fastapi import APIRouter, Depends

from ..deps import get_components, get_conversations
from ..schemas import ChatRequest, ChatResponse
from ...main import AppComponents

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def post_chat(
    body: ChatRequest,
    components: AppComponents = Depends(get_components),
    conversations: dict = Depends(get_conversations),
) -> ChatResponse:
    prior_history = conversations.get(body.conversation_id, [])
    result = await components.orchestrator.handle_query(body.message, history=prior_history)

    assistant_content = result.clarification_question if result.needs_clarification else result.answer
    conversations[body.conversation_id] = prior_history + [
        {"role": "user", "content": body.message},
        {"role": "assistant", "content": assistant_content or ""},
    ]

    return ChatResponse(
        answer=result.answer,
        dropped_claims=result.dropped_claims,
        needs_clarification=result.needs_clarification,
        clarification_question=result.clarification_question,
    )
```

In `civicpilot/api/app.py`, add the import and router registration alongside the agencies router:

```python
from .routes.chat import router as chat_router
```

and:

```python
    app.include_router(chat_router, prefix="/api")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_chat_routes.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full backend suite**

Run: `pytest tests/ -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add civicpilot/api/routes/chat.py civicpilot/api/app.py tests/api/test_chat_routes.py
git commit -m "feat: add POST /api/chat endpoint with in-memory conversation history"
```

---

## Task 8: Backend docs

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Update `.env.example`**

Add a line documenting the new optional CORS setting:

```
# Optional: origin allowed to call the API (defaults to the Vite dev server)
CORS_ORIGIN=http://localhost:5173
```

- [ ] **Step 2: Add an API section to `README.md`**

After the existing "## Run" section, add:

```markdown
## Run the API

The frontend (see `frontend/README.md`) talks to a FastAPI backend:

```
uvicorn civicpilot.api.app:app --reload --port 8000
```

Set `CORS_ORIGIN` in `.env` if the frontend isn't running on the Vite default
(`http://localhost:5173`).
```

- [ ] **Step 3: Commit**

```bash
git add README.md .env.example
git commit -m "docs: document running the FastAPI backend"
```

---

## Task 9: Frontend project scaffold

**Files:**
- Create: `frontend/` (via Vite CLI — package.json, tsconfig.json, vite.config.ts, index.html, src/main.tsx, src/App.tsx, src/index.css get generated, then modified below)
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/src/index.css`
- Create: `frontend/src/test/setup.ts`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/package.json`
- Modify: `.gitignore`

**Interfaces:**
- Produces: Tailwind theme tokens (`bg-paper`, `text-ink`, `text-primary`, `border-hairline`, `text-verified`, `text-unverified`, `text-destructive`, `text-muted`, `font-serif`/`font-sans`/`font-mono`) used by every component task from here on. Vitest configured with `jsdom` + React Testing Library, used by every `*.test.tsx` from here on.

- [ ] **Step 1: Scaffold the Vite project**

From the repo root:

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

- [ ] **Step 2: Install project dependencies**

Still inside `frontend/`:

```bash
npm install recharts clsx tailwind-merge class-variance-authority
npm install -D tailwindcss@3 postcss autoprefixer vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
npx tailwindcss init -p
```

- [ ] **Step 3: Configure Tailwind with the Docket Ledger tokens**

Replace `frontend/tailwind.config.js`:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F6F7F9",
        card: "#FFFFFF",
        ink: "#12172B",
        primary: "#1D2A54",
        verified: "#146C43",
        unverified: "#A15C07",
        destructive: "#B91C1C",
        hairline: "#DADFE7",
        muted: "#5B6472",
      },
      fontFamily: {
        serif: ["Newsreader", "Georgia", "serif"],
        sans: ["IBM Plex Sans", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 4: Wire Tailwind and the Docket Ledger fonts into the global stylesheet**

Replace `frontend/src/index.css`:

```css
@import url('https://fonts.googleapis.com/css2?family=Newsreader:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  @apply bg-paper text-ink font-sans;
}
```

- [ ] **Step 5: Configure Vitest**

Replace `frontend/vite.config.ts`:

```ts
/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
});
```

Create `frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
// @ts-expect-error jsdom doesn't implement ResizeObserver
global.ResizeObserver = ResizeObserverMock;
```

Add a test script to `frontend/package.json`'s `"scripts"` block:

```json
"test": "vitest run"
```

- [ ] **Step 6: Add a `VITE_API_BASE_URL` default and update `.gitignore`**

Create `frontend/.env.example`:

```
VITE_API_BASE_URL=http://localhost:8000
```

In the repo-root `.gitignore`, add:

```
frontend/node_modules/
frontend/dist/
frontend/.env
```

- [ ] **Step 7: Verify the scaffold builds and runs**

From `frontend/`:

```bash
npm run build
```

Expected: builds successfully with no errors (default Vite counter app still in place at this point — it gets replaced in Task 15).

- [ ] **Step 8: Commit**

```bash
git add frontend .gitignore
git commit -m "chore: scaffold frontend (Vite + React + TS + Tailwind + Vitest)

Docket Ledger design tokens (color/type) wired into Tailwind config;
component work starts in the next task."
```

---

## Task 10: `cn` utility + hand-authored shadcn-style `Button`/`Input`

**Why hand-authored rather than the `shadcn` CLI:** shadcn/ui's own model is "copy the component source into your repo," not a runtime package — hand-writing the canonical `Button`/`Input` source with `class-variance-authority` (already installed in Task 9) delivers the same thing without depending on a CLI whose exact prompts/defaults can drift between versions.

**Files:**
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/components/ui/button.tsx`
- Create: `frontend/src/components/ui/input.tsx`
- Create: `frontend/src/components/ui/button.test.tsx`
- Create: `frontend/src/components/ui/input.test.tsx`

**Interfaces:**
- Produces: `cn(...inputs: ClassValue[]) -> string`. `<Button variant?="default"|"outline" size?="default"|"sm" ...HTMLButtonAttributes>`, `<Input ...HTMLInputAttributes>` — both `h-11` (44px) by default per touch-target accessibility guidance, used by Tasks 12-14.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/ui/button.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./button";

describe("Button", () => {
  it("renders its label and responds to clicks", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Retry</Button>);

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(onClick).toHaveBeenCalledOnce();
  });

  it("is disabled when the disabled prop is set", () => {
    render(<Button disabled>Send</Button>);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});
```

Create `frontend/src/components/ui/input.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Input } from "./input";

describe("Input", () => {
  it("accepts typed input", async () => {
    render(<Input aria-label="Search agencies" />);
    const input = screen.getByLabelText("Search agencies");

    await userEvent.type(input, "Energy");

    expect(input).toHaveValue("Energy");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`): `npm run test`
Expected: FAIL — `Cannot find module './button'` / `'./input'`

- [ ] **Step 3: Implement**

Create `frontend/src/lib/utils.ts`:

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

Create `frontend/src/components/ui/button.tsx`:

```tsx
import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded text-xs font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary",
  {
    variants: {
      variant: {
        default: "bg-primary text-white hover:bg-primary/90",
        outline: "border border-hairline bg-transparent text-ink hover:bg-paper",
      },
      size: {
        default: "h-11 px-4",
        sm: "h-9 px-3",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  )
);
Button.displayName = "Button";
```

Create `frontend/src/components/ui/input.tsx`:

```tsx
import { type InputHTMLAttributes, forwardRef } from "react";
import { cn } from "../../lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-11 w-full rounded border border-hairline bg-paper px-3 py-2 text-xs text-ink placeholder:text-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `frontend/`): `npm run test`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/utils.ts frontend/src/components/ui
git commit -m "feat: add cn utility and Button/Input primitives"
```

---

## Task 11: API client module

**Files:**
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/client.test.ts`

**Interfaces:**
- Produces: `AgencySummary`, `ObligationYear`, `RuleSummary`, `AgencyDashboard`, `ChatResponse` types (mirroring `civicpilot/api/schemas.py` field-for-field). `fetchAgencies()`, `fetchDashboard(toptierCode)`, `postChat(conversationId, message)` — used by every component task from here on.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/client.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchAgencies, fetchDashboard, postChat } from "./client";

const originalFetch = global.fetch;

beforeEach(() => {
  global.fetch = vi.fn();
});

afterEach(() => {
  global.fetch = originalFetch;
});

describe("api client", () => {
  it("fetchAgencies calls GET /api/agencies and returns parsed JSON", async () => {
    const agencies = [{ name: "EPA", toptier_code: "068", fr_slug: "environmental-protection-agency" }];
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => agencies,
    });

    const result = await fetchAgencies();

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/agencies"),
      expect.objectContaining({}),
    );
    expect(result).toEqual(agencies);
  });

  it("fetchDashboard calls the agency-scoped dashboard route", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ name: "EPA" }),
    });

    await fetchDashboard("068");

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/agencies/068/dashboard"),
      expect.objectContaining({}),
    );
  });

  it("postChat sends conversation_id and message as JSON", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ answer: "Fine.", dropped_claims: [], needs_clarification: false, clarification_question: null }),
    });

    await postChat("conv-1", "What did EPA spend?");

    const [, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ conversation_id: "conv-1", message: "What did EPA spend?" });
  });

  it("throws when the response is not ok", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });

    await expect(fetchAgencies()).rejects.toThrow();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npm run test`
Expected: FAIL — `Cannot find module './client'`

- [ ] **Step 3: Implement**

Create `frontend/src/api/types.ts`:

```ts
export interface AgencySummary {
  name: string;
  toptier_code: string;
  fr_slug: string | null;
}

export interface ObligationYear {
  fiscal_year: number;
  amount: number;
  partial: boolean;
}

export interface RuleSummary {
  document_number: string;
  title: string;
  type: string;
  publication_date: string;
  html_url: string;
}

export interface AgencyDashboard {
  name: string;
  toptier_code: string;
  fr_slug: string | null;
  obligations: ObligationYear[];
  rules: RuleSummary[];
}

export interface ChatResponse {
  answer: string;
  dropped_claims: string[];
  needs_clarification: boolean;
  clarification_question: string | null;
}
```

Create `frontend/src/api/client.ts`:

```ts
import type { AgencyDashboard, AgencySummary, ChatResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    throw new Error(`Request to ${path} failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchAgencies(): Promise<AgencySummary[]> {
  return request<AgencySummary[]>("/api/agencies");
}

export function fetchDashboard(toptierCode: string): Promise<AgencyDashboard> {
  return request<AgencyDashboard>(`/api/agencies/${toptierCode}/dashboard`);
}

export function postChat(conversationId: string, message: string): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ conversation_id: conversationId, message }),
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `frontend/`): `npm run test`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api
git commit -m "feat: add typed API client for agencies/dashboard/chat endpoints"
```

---

## Task 12: `CitationStamp` + inline answer rendering

**Files:**
- Create: `frontend/src/components/CitationStamp.tsx`
- Create: `frontend/src/components/CitationStamp.test.tsx`
- Create: `frontend/src/components/renderAnswerWithStamps.tsx`
- Create: `frontend/src/components/renderAnswerWithStamps.test.tsx`

**Interfaces:**
- Produces: `<CitationStamp label variant="verified"|"unverified" href?>`, `renderAnswerWithStamps(text: string) -> ReactNode[]` — used by Task 14 (dashboard rules list, passes `href`) and Task 15 (chat answers, never passes `href` — the model's plain-text answer carries only the citation ID, not a URL, so chat-rendered stamps are intentionally never clickable; see the spec's "Citation stamp clicks" note).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/CitationStamp.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CitationStamp } from "./CitationStamp";

describe("CitationStamp", () => {
  it("renders a verified citation as a bracketed label", () => {
    render(<CitationStamp label="doc:2026-1" variant="verified" />);
    expect(screen.getByText("[doc:2026-1]")).toBeInTheDocument();
  });

  it("renders as a link when href is provided", () => {
    render(<CitationStamp label="doc:2026-1" variant="verified" href="https://example.com/doc" />);
    expect(screen.getByRole("link", { name: "[doc:2026-1]" })).toHaveAttribute(
      "href", "https://example.com/doc",
    );
  });

  it("renders as plain text (no link) when href is omitted", () => {
    render(<CitationStamp label="award:068-FY2026" variant="verified" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders the unverified variant without brackets", () => {
    render(<CitationStamp label="UNVERIFIED MATCH" variant="unverified" />);
    expect(screen.getByText("UNVERIFIED MATCH")).toBeInTheDocument();
  });
});
```

Create `frontend/src/components/renderAnswerWithStamps.test.tsx`:

```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderAnswerWithStamps } from "./renderAnswerWithStamps";

describe("renderAnswerWithStamps", () => {
  it("splits plain text around citation markers into stamps", () => {
    const { container } = render(
      <div>{renderAnswerWithStamps("EPA spent $1B [award:068-FY2026] this year.")}</div>
    );
    expect(container.textContent).toBe("EPA spent $1B [award:068-FY2026] this year.");
    expect(container.querySelectorAll("span, a").length).toBeGreaterThanOrEqual(1);
  });

  it("handles text with no citations", () => {
    const { container } = render(<div>{renderAnswerWithStamps("Did you mean this year?")}</div>);
    expect(container.textContent).toBe("Did you mean this year?");
  });

  it("handles multiple citations", () => {
    const { container } = render(
      <div>{renderAnswerWithStamps("Two rules [doc:1] and [doc:2] apply.")}</div>
    );
    expect(container.textContent).toBe("Two rules [doc:1] and [doc:2] apply.");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`): `npm run test`
Expected: FAIL — modules don't exist yet

- [ ] **Step 3: Implement**

Create `frontend/src/components/CitationStamp.tsx`:

```tsx
export interface CitationStampProps {
  label: string;
  variant: "verified" | "unverified";
  href?: string;
}

export function CitationStamp({ label, variant, href }: CitationStampProps) {
  const colorClasses =
    variant === "verified" ? "border-verified text-verified" : "border-unverified text-unverified";
  const className = `inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[11px] tracking-wide ${colorClasses}`;
  const content = variant === "verified" ? `[${label}]` : label;

  if (href) {
    return (
      <a className={className} href={href} target="_blank" rel="noreferrer">
        {content}
      </a>
    );
  }
  return <span className={className}>{content}</span>;
}
```

Create `frontend/src/components/renderAnswerWithStamps.tsx`:

```tsx
import type { ReactNode } from "react";
import { CitationStamp } from "./CitationStamp";

const CITATION_PATTERN = /\[(doc|award):([\w-]+)\]/g;

export function renderAnswerWithStamps(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  CITATION_PATTERN.lastIndex = 0;
  while ((match = CITATION_PATTERN.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const [, kind, id] = match;
    parts.push(<CitationStamp key={`stamp-${key++}`} label={`${kind}:${id}`} variant="verified" />);
    lastIndex = CITATION_PATTERN.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `frontend/`): `npm run test`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CitationStamp.tsx frontend/src/components/CitationStamp.test.tsx frontend/src/components/renderAnswerWithStamps.tsx frontend/src/components/renderAnswerWithStamps.test.tsx
git commit -m "feat: add CitationStamp and inline citation rendering"
```

---

## Task 13: `AgencyRail`

**Files:**
- Create: `frontend/src/components/AgencyRail.tsx`
- Create: `frontend/src/components/AgencyRail.test.tsx`

**Interfaces:**
- Consumes: `AgencySummary` (Task 11), `Input` (Task 10).
- Produces: `<AgencyRail agencies selectedToptierCode onSelect>` — used by Task 15 (App shell).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/AgencyRail.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AgencyRail } from "./AgencyRail";
import type { AgencySummary } from "../api/types";

const agencies: AgencySummary[] = [
  { name: "Environmental Protection Agency", toptier_code: "068", fr_slug: "environmental-protection-agency" },
  { name: "Department of Energy", toptier_code: "089", fr_slug: "energy-department" },
];

describe("AgencyRail", () => {
  it("lists every agency with its toptier code", () => {
    render(<AgencyRail agencies={agencies} selectedToptierCode={null} onSelect={vi.fn()} />);
    expect(screen.getByText("Environmental Protection Agency")).toBeInTheDocument();
    expect(screen.getByText("068")).toBeInTheDocument();
  });

  it("filters the list as the user types", async () => {
    render(<AgencyRail agencies={agencies} selectedToptierCode={null} onSelect={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Search agencies"), "Energy");

    expect(screen.getByText("Department of Energy")).toBeInTheDocument();
    expect(screen.queryByText("Environmental Protection Agency")).not.toBeInTheDocument();
  });

  it("calls onSelect with the clicked agency", async () => {
    const onSelect = vi.fn();
    render(<AgencyRail agencies={agencies} selectedToptierCode={null} onSelect={onSelect} />);

    await userEvent.click(screen.getByText("Department of Energy"));

    expect(onSelect).toHaveBeenCalledWith(agencies[1]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npm run test`
Expected: FAIL — `Cannot find module './AgencyRail'`

- [ ] **Step 3: Implement**

Create `frontend/src/components/AgencyRail.tsx`:

```tsx
import { useMemo, useState } from "react";
import type { AgencySummary } from "../api/types";
import { Input } from "./ui/input";

export interface AgencyRailProps {
  agencies: AgencySummary[];
  selectedToptierCode: string | null;
  onSelect: (agency: AgencySummary) => void;
}

export function AgencyRail({ agencies, selectedToptierCode, onSelect }: AgencyRailProps) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return agencies;
    return agencies.filter((agency) => agency.name.toLowerCase().includes(q));
  }, [agencies, query]);

  return (
    <nav className="w-full shrink-0 border-hairline bg-card md:w-[220px] md:border-r" aria-label="Agencies">
      <div className="p-3">
        <Input
          placeholder="Search agencies…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search agencies"
        />
      </div>
      <ul>
        {filtered.map((agency) => (
          <li key={agency.toptier_code}>
            <button
              type="button"
              onClick={() => onSelect(agency)}
              className={`flex min-h-11 w-full items-center justify-between px-3.5 py-2 text-left text-sm ${
                agency.toptier_code === selectedToptierCode
                  ? "border-l-2 border-primary bg-paper font-semibold"
                  : ""
              }`}
            >
              <span>{agency.name}</span>
              <span className="font-mono text-[10px] text-muted">{agency.toptier_code}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `frontend/`): `npm run test`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AgencyRail.tsx frontend/src/components/AgencyRail.test.tsx
git commit -m "feat: add AgencyRail component"
```

---

## Task 14: `AgencyRecord`

**Files:**
- Create: `frontend/src/components/chartData.ts`
- Create: `frontend/src/components/chartData.test.ts`
- Create: `frontend/src/components/AgencyRecord.tsx`
- Create: `frontend/src/components/AgencyRecord.test.tsx`

**Interfaces:**
- Consumes: `fetchDashboard` (Task 11), `CitationStamp` (Task 12), `Button` (Task 10).
- Produces: `buildChartData(obligations: ObligationYear[]) -> {fiscalYear: string, amount: number}[]` (pure, unit-tested separately to avoid asserting on Recharts' jsdom-fragile SVG internals). `<AgencyRecord toptierCode>` — used by Task 15.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/chartData.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { buildChartData } from "./chartData";

describe("buildChartData", () => {
  it("labels the partial fiscal year distinctly from closed years", () => {
    const result = buildChartData([
      { fiscal_year: 2024, amount: 100, partial: false },
      { fiscal_year: 2025, amount: 200, partial: false },
      { fiscal_year: 2026, amount: 50, partial: true },
    ]);

    expect(result).toEqual([
      { fiscalYear: "FY2024", amount: 100 },
      { fiscalYear: "FY2025", amount: 200 },
      { fiscalYear: "FY2026 (partial)", amount: 50 },
    ]);
  });
});
```

Create `frontend/src/components/AgencyRecord.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AgencyRecord } from "./AgencyRecord";
import { fetchDashboard } from "../api/client";

vi.mock("../api/client", () => ({
  fetchDashboard: vi.fn(),
}));

const mockDashboard = {
  name: "Environmental Protection Agency",
  toptier_code: "068",
  fr_slug: "environmental-protection-agency",
  obligations: [
    { fiscal_year: 2024, amount: 27274197006.76, partial: false },
    { fiscal_year: 2025, amount: 29100000000, partial: false },
    { fiscal_year: 2026, amount: 10797760149.61, partial: true },
  ],
  rules: [
    {
      document_number: "2026-16627",
      title: "National Emission Standards",
      type: "RULE",
      publication_date: "2026-08-01",
      html_url: "https://www.federalregister.gov/documents/2026-16627",
    },
  ],
};

describe("AgencyRecord", () => {
  it("renders the agency name and rules after loading", async () => {
    vi.mocked(fetchDashboard).mockResolvedValue(mockDashboard);
    render(<AgencyRecord toptierCode="068" />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Environmental Protection Agency")).toBeInTheDocument());

    expect(screen.getByText("National Emission Standards")).toBeInTheDocument();
    expect(screen.getByText("[doc:2026-16627]")).toBeInTheDocument();
  });

  it("shows an error state with a working retry button", async () => {
    vi.mocked(fetchDashboard).mockRejectedValueOnce(new Error("network error"));
    render(<AgencyRecord toptierCode="068" />);

    await waitFor(() => expect(screen.getByText(/couldn't load/i)).toBeInTheDocument());

    vi.mocked(fetchDashboard).mockResolvedValueOnce(mockDashboard);
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => expect(screen.getByText("Environmental Protection Agency")).toBeInTheDocument());
  });

  it("shows empty-state text when there is no data", async () => {
    vi.mocked(fetchDashboard).mockResolvedValue({ ...mockDashboard, obligations: [], rules: [] });
    render(<AgencyRecord toptierCode="068" />);

    await waitFor(() => expect(screen.getByText(/no obligation data available/i)).toBeInTheDocument());
    expect(screen.getByText(/no final rules issued/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`): `npm run test`
Expected: FAIL — modules don't exist yet

- [ ] **Step 3: Implement**

Create `frontend/src/components/chartData.ts`:

```ts
import type { ObligationYear } from "../api/types";

export interface ChartPoint {
  fiscalYear: string;
  amount: number;
}

export function buildChartData(obligations: ObligationYear[]): ChartPoint[] {
  return obligations.map((o) => ({
    fiscalYear: `FY${o.fiscal_year}${o.partial ? " (partial)" : ""}`,
    amount: o.amount,
  }));
}
```

Create `frontend/src/components/AgencyRecord.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { fetchDashboard } from "../api/client";
import type { AgencyDashboard } from "../api/types";
import { buildChartData } from "./chartData";
import { CitationStamp } from "./CitationStamp";
import { Button } from "./ui/button";

export interface AgencyRecordProps {
  toptierCode: string;
}

type LoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; dashboard: AgencyDashboard };

export function AgencyRecord({ toptierCode }: AgencyRecordProps) {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    fetchDashboard(toptierCode)
      .then((dashboard) => {
        if (!cancelled) setState({ status: "ready", dashboard });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [toptierCode]);

  if (state.status === "loading") {
    return <div className="p-6 text-sm text-muted">Loading…</div>;
  }

  if (state.status === "error") {
    return (
      <div className="p-6 text-sm text-muted">
        <p>Couldn't load this agency's data.</p>
        <Button variant="outline" size="sm" className="mt-2" onClick={() => setState({ status: "loading" })}>
          Retry
        </Button>
      </div>
    );
  }

  const { dashboard } = state;
  const chartData = buildChartData(dashboard.obligations);

  return (
    <div className="p-6">
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted">Agency record</div>
      <h1 className="mt-1 font-serif text-2xl font-medium text-ink">{dashboard.name}</h1>
      <div className="font-mono text-[11px] tracking-wide text-muted">
        TOPTIER {dashboard.toptier_code}
        {dashboard.fr_slug ? ` · FR SLUG ${dashboard.fr_slug}` : ""}
      </div>

      <h2 className="mt-6 border-b border-hairline pb-1.5 text-xs uppercase tracking-wider text-muted">
        Obligations by fiscal year
      </h2>
      {dashboard.obligations.length === 0 ? (
        <p className="mt-3 text-sm text-muted">No obligation data available for this agency.</p>
      ) : (
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={chartData}>
            <XAxis dataKey="fiscalYear" fontSize={10} />
            <YAxis hide />
            <Bar dataKey="amount" fill="#1D2A54" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}

      <h2 className="mt-6 border-b border-hairline pb-1.5 text-xs uppercase tracking-wider text-muted">
        Final rules — last 12 months
      </h2>
      {dashboard.rules.length === 0 ? (
        <p className="mt-3 text-sm text-muted">No final rules issued in the last 12 months.</p>
      ) : (
        <ul>
          {dashboard.rules.map((rule) => (
            <li key={rule.document_number} className="flex items-baseline gap-3.5 border-t border-hairline py-2.5 text-sm">
              <span className="w-24 shrink-0 font-mono text-ink">{rule.document_number}</span>
              <span className="flex-1 text-ink">{rule.title}</span>
              <span className="w-20 shrink-0 text-right font-mono text-[11px] text-muted">{rule.publication_date}</span>
              <CitationStamp label={`doc:${rule.document_number}`} variant="verified" href={rule.html_url} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `frontend/`): `npm run test`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chartData.ts frontend/src/components/chartData.test.ts frontend/src/components/AgencyRecord.tsx frontend/src/components/AgencyRecord.test.tsx
git commit -m "feat: add AgencyRecord (spending chart + final-rules list)"
```

---

## Task 15: `InquiryPanel`

**Files:**
- Create: `frontend/src/components/InquiryPanel.tsx`
- Create: `frontend/src/components/InquiryPanel.test.tsx`

**Interfaces:**
- Consumes: `postChat` (Task 11), `renderAnswerWithStamps` (Task 12), `Input` (Task 10).
- Produces: `<InquiryPanel conversationId>` — used by Task 16.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/InquiryPanel.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { InquiryPanel } from "./InquiryPanel";
import { postChat } from "../api/client";

vi.mock("../api/client", () => ({
  postChat: vi.fn(),
}));

describe("InquiryPanel", () => {
  it("sends a message on Enter and renders the cited answer", async () => {
    vi.mocked(postChat).mockResolvedValue({
      answer: "EPA spent $1B [award:068-FY2026].",
      dropped_claims: [],
      needs_clarification: false,
      clarification_question: null,
    });
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend?{Enter}");

    expect(screen.getByText("What did EPA spend?")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/EPA spent \$1B/)).toBeInTheDocument());
    expect(postChat).toHaveBeenCalledWith("conv-1", "What did EPA spend?");
  });

  it("shows a dropped-claims caption when claims were omitted", async () => {
    vi.mocked(postChat).mockResolvedValue({
      answer: "EPA spent $1B [award:068-FY2026].",
      dropped_claims: ["unsupported claim one", "unsupported claim two"],
      needs_clarification: false,
      clarification_question: null,
    });
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend?{Enter}");

    await waitFor(() => expect(screen.getByText(/2 unverifiable claims omitted/)).toBeInTheDocument());
  });

  it("renders a clarification response distinctly from a normal answer", async () => {
    vi.mocked(postChat).mockResolvedValue({
      answer: "",
      dropped_claims: [],
      needs_clarification: true,
      clarification_question: "Calendar year or fiscal year?",
    });
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend this year?{Enter}");

    await waitFor(() => expect(screen.getByText("Calendar year or fiscal year?")).toBeInTheDocument());
  });

  it("shows an error bubble when the request fails", async () => {
    vi.mocked(postChat).mockRejectedValue(new Error("network error"));
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend?{Enter}");

    await waitFor(() => expect(screen.getByText(/something went wrong/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npm run test`
Expected: FAIL — `Cannot find module './InquiryPanel'`

- [ ] **Step 3: Implement**

Create `frontend/src/components/InquiryPanel.tsx`:

```tsx
import { useState } from "react";
import { postChat } from "../api/client";
import { renderAnswerWithStamps } from "./renderAnswerWithStamps";
import { Input } from "./ui/input";

export interface InquiryPanelProps {
  conversationId: string;
}

interface Turn {
  role: "user" | "answer" | "clarification" | "error";
  text: string;
  droppedCount?: number;
}

export function InquiryPanel({ conversationId }: InquiryPanelProps) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  async function send() {
    const message = draft.trim();
    if (!message || sending) return;
    setDraft("");
    setTurns((prev) => [...prev, { role: "user", text: message }]);
    setSending(true);
    try {
      const response = await postChat(conversationId, message);
      if (response.needs_clarification) {
        setTurns((prev) => [...prev, { role: "clarification", text: response.clarification_question ?? "" }]);
      } else {
        setTurns((prev) => [
          ...prev,
          { role: "answer", text: response.answer, droppedCount: response.dropped_claims.length },
        ]);
      }
    } catch {
      setTurns((prev) => [...prev, { role: "error", text: "Something went wrong — try again." }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex w-full shrink-0 flex-col border-hairline bg-card md:w-[290px] md:border-l">
      <div className="border-b border-hairline p-3.5 font-mono text-xs uppercase tracking-wider text-muted">
        Inquiry log
      </div>
      <div className="flex-1 space-y-3.5 overflow-y-auto p-4">
        {turns.map((turn, index) => {
          if (turn.role === "user") {
            return (
              <div key={index} className="ml-auto max-w-[85%] rounded-lg rounded-br-sm bg-paper px-2.5 py-2 text-xs">
                {turn.text}
              </div>
            );
          }
          if (turn.role === "clarification") {
            return (
              <div key={index} className="rounded border border-primary/40 bg-paper px-2.5 py-2 text-xs text-ink">
                {turn.text}
              </div>
            );
          }
          if (turn.role === "error") {
            return (
              <div key={index} className="rounded border border-destructive/40 px-2.5 py-2 text-xs text-destructive">
                {turn.text}
              </div>
            );
          }
          return (
            <div key={index} className="border-t-2 border-primary pt-2 text-xs leading-relaxed text-ink">
              <div>{renderAnswerWithStamps(turn.text)}</div>
              {!!turn.droppedCount && (
                <div className="mt-1.5 font-mono text-[10px] text-muted">
                  {turn.droppedCount} unverifiable claim{turn.droppedCount === 1 ? "" : "s"} omitted
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="border-t border-hairline p-3">
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") send();
          }}
          placeholder="Ask a follow-up…"
          aria-label="Ask a follow-up question"
          disabled={sending}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `frontend/`): `npm run test`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/InquiryPanel.tsx frontend/src/components/InquiryPanel.test.tsx
git commit -m "feat: add InquiryPanel (chat with clarification/error/dropped-claims states)"
```

---

## Task 16: App shell — composition, responsive collapse, docs, and live verification

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/App.test.tsx`
- Modify: `frontend/src/main.tsx`
- Create: `frontend/README.md`
- Delete: `frontend/src/App.css` (Vite template default styling, superseded by Tailwind)

**Interfaces:**
- Consumes: `AgencyRail` (Task 13), `AgencyRecord` (Task 14), `InquiryPanel` (Task 15), `fetchAgencies` (Task 11).
- Produces: the assembled app — nothing downstream depends on this.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/App.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { fetchAgencies, fetchDashboard } from "./api/client";

vi.mock("./api/client", () => ({
  fetchAgencies: vi.fn(),
  fetchDashboard: vi.fn(),
  postChat: vi.fn(),
}));

describe("App", () => {
  it("loads agencies, shows a placeholder before selection, and loads the dashboard on select", async () => {
    vi.mocked(fetchAgencies).mockResolvedValue([
      { name: "Environmental Protection Agency", toptier_code: "068", fr_slug: "environmental-protection-agency" },
    ]);
    vi.mocked(fetchDashboard).mockResolvedValue({
      name: "Environmental Protection Agency",
      toptier_code: "068",
      fr_slug: "environmental-protection-agency",
      obligations: [],
      rules: [],
    });

    render(<App />);

    expect(screen.getByText(/select an agency/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Environmental Protection Agency")).toBeInTheDocument());

    await userEvent.click(screen.getByText("Environmental Protection Agency"));

    await waitFor(() => expect(fetchDashboard).toHaveBeenCalledWith("068"));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npm run test`
Expected: FAIL — current `App.tsx` is still the Vite counter template

- [ ] **Step 3: Implement**

Delete `frontend/src/App.css` (the Vite template's default styles — Tailwind utilities replace it).

Replace `frontend/src/App.tsx`:

```tsx
import { useEffect, useState } from "react";
import { fetchAgencies } from "./api/client";
import type { AgencySummary } from "./api/types";
import { AgencyRail } from "./components/AgencyRail";
import { AgencyRecord } from "./components/AgencyRecord";
import { InquiryPanel } from "./components/InquiryPanel";
import { Button } from "./components/ui/button";

function newConversationId(): string {
  return crypto.randomUUID();
}

export function App() {
  const [agencies, setAgencies] = useState<AgencySummary[]>([]);
  const [selected, setSelected] = useState<AgencySummary | null>(null);
  const [conversationId, setConversationId] = useState<string>(() => newConversationId());
  const [railOpen, setRailOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    fetchAgencies().then(setAgencies).catch(() => setAgencies([]));
  }, []);

  function handleSelect(agency: AgencySummary) {
    setSelected(agency);
    setConversationId(newConversationId());
    setRailOpen(false);
  }

  return (
    <div className="flex h-screen flex-col bg-paper text-ink md:flex-row">
      <div className="flex items-center justify-between border-b border-hairline bg-card p-3 md:hidden">
        <Button variant="outline" size="sm" onClick={() => setRailOpen(true)}>
          Agencies
        </Button>
        <span className="font-serif text-sm">{selected?.name ?? "CivicPilot"}</span>
        <Button variant="outline" size="sm" onClick={() => setChatOpen(true)}>
          Ask
        </Button>
      </div>

      <div className={`${railOpen ? "fixed inset-0 z-20 bg-paper" : "hidden"} md:relative md:z-auto md:block`}>
        {railOpen && (
          <Button variant="outline" size="sm" className="m-2 md:hidden" onClick={() => setRailOpen(false)}>
            Close
          </Button>
        )}
        <AgencyRail agencies={agencies} selectedToptierCode={selected?.toptier_code ?? null} onSelect={handleSelect} />
      </div>

      <main className="flex-1 overflow-y-auto">
        {selected ? (
          <AgencyRecord toptierCode={selected.toptier_code} />
        ) : (
          <div className="p-6 text-sm text-muted">Select an agency to view its record.</div>
        )}
      </main>

      <div className={`${chatOpen ? "fixed inset-x-0 bottom-0 z-20 h-[70vh]" : "hidden"} md:relative md:z-auto md:block md:h-auto`}>
        {chatOpen && (
          <Button variant="outline" size="sm" className="m-2 md:hidden" onClick={() => setChatOpen(false)}>
            Close
          </Button>
        )}
        <InquiryPanel conversationId={conversationId} />
      </div>
    </div>
  );
}
```

Update `frontend/src/main.tsx` to match the named export:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `frontend/`): `npm run test`
Expected: all PASS

- [ ] **Step 5: Run the full frontend suite and production build**

Run (from `frontend/`):

```bash
npm run test
npm run build
```

Expected: all tests PASS, build succeeds with no TypeScript errors.

- [ ] **Step 6: Write `frontend/README.md`**

```markdown
# CivicPilot Frontend

React + Vite + Tailwind dashboard and chat UI for CivicPilot.

## Setup

```
npm install
cp .env.example .env
```

`VITE_API_BASE_URL` defaults to `http://localhost:8000` — point it at wherever
the FastAPI backend (see the repo-root README's "Run the API" section) is
running.

## Run

```
npm run dev
```

## Test

```
npm run test
```

## Build

```
npm run build
```
```

- [ ] **Step 7: Manual live verification**

With the backend running (`uvicorn civicpilot.api.app:app --reload --port 8000`, real `GROQ_API_KEY`/`OPENROUTER_API_KEY` in `.env`) and the frontend running (`npm run dev` in `frontend/`), open the app in a browser and verify by hand — this is the step that catches what the mocked test suite can't, matching how the two production bugs earlier today were actually found:

1. The agency rail loads real agencies from the crosswalk and filters as you type.
2. Selecting an agency loads a real spending chart (3 fiscal years, current year visually marked partial) and a real final-rules list from the live Federal Register API.
3. Clicking a `[doc:...]` stamp opens the real Federal Register document in a new tab.
4. Asking a question in the Inquiry Log returns a real cited answer from Groq (or the OpenRouter fallback), with citation stamps rendered inline.
5. A follow-up question that references the prior answer (e.g. "what about last year?") gets a coherent response — confirms multi-turn history is actually wired through, not just accepted as a parameter.
6. Resize the browser below 768px and below 1024px — confirm the rail and chat panel collapse into the toggle-button pattern and are usable via touch/click.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/main.tsx frontend/README.md
git rm frontend/src/App.css
git commit -m "feat: assemble App shell with responsive rail/chat collapse

Manually verified end-to-end against live Groq/FR/USAspending APIs,
including multi-turn chat and the sub-768px/sub-1024px responsive
collapse, not just the mocked component suite."
```
