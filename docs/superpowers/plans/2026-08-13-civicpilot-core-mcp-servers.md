# CivicPilot Core (Federal Register + USAspending + Orchestration) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working, testable, end-to-end slice of CivicPilot: a Federal Register MCP server, a USAspending MCP server (with its hybrid async query pattern), the shared agency crosswalk and cache, and an orchestrator that answers the flagship query ("What EPA rules were proposed this quarter, and what's the related spending?") with cited, groundedness-enforced answers — without yet needing the RAG layer, the fine-tuned router, evals infrastructure, or deployment packaging (later plans).

**Architecture:** Two independent MCP servers (Federal Register, USAspending) built on the official `mcp` Python SDK's `FastMCP`, each wrapping a thin async HTTP client with source-specific action-enum tools. A shared static agency crosswalk resolves plain-language agency names to per-source identifiers, with fuzzy matches always flagged unverified. An orchestrator runs a bounded LLM tool-calling loop against both servers (invoked in-process, not over a transport — see Global Constraints), detects fiscal-year/calendar-year ambiguity before querying, and enforces citation markers on every factual claim in the final answer before returning it.

**Tech Stack:** Python 3.11+, `httpx` (async HTTP), `mcp` (FastMCP), `rapidfuzz` (fuzzy agency matching), `pytest` + `pytest-asyncio` + `respx` (testing, all HTTP mocked).

**Spec:** [docs/superpowers/specs/2026-08-13-civicpilot-design.md](../specs/2026-08-13-civicpilot-design.md)

## Global Constraints

- Python 3.11+, async-first throughout (`httpx.AsyncClient`, `async def`).
- Every outbound HTTP call to Federal Register or USAspending goes through `QueryCache` (Task 2) before hitting the live API.
- MCP tools use action-enum consolidation: one tool per source capability with an `action` parameter, not one tool per endpoint.
- Agency names are resolved via the static crosswalk (Task 3) **only at the orchestration layer** — the FR/USAspending clients and servers operate strictly on already-resolved IDs (`agency_slug`, `toptier_code`), never raw agency names.
- Fuzzy crosswalk matches are always flagged `verified=False` and surfaced back to the caller — never silently trusted, regardless of match confidence.
- No live network calls in any test — all HTTP mocked via `respx`. The full test suite must pass with no network access.
- Every final answer enforces citation markers (`[doc:...]` / `[award:...]`) on factual claims before being returned; uncited factual sentences are dropped, not passed through.
- USAspending's async bulk-download pattern uses bounded internal polling (~8s) before returning a job handle — it never blocks indefinitely.
- Single-process, in-process composition: both MCP servers expose real `FastMCP` tool schemas, but in this plan the orchestrator invokes their implementation functions directly in-process (no stdio/network transport). Transport wiring is deferred to the deployment plan (spec Phase 7).
- LLM provider for this plan: Groq, model `moonshotai/kimi-k2-instruct`. Cerebras/Qwen3 fallback and retry/backoff logic are deferred to the deployment plan.
- Date handling note (refines spec prose): calendar quarters and federal fiscal quarters are the same 3-month windows just numbered differently, so "this quarter" never actually diverges between the two conventions — only the FY *label* differs. "This year" (calendar vs. fiscal year) is the genuine divergence case and is where elicitation actually matters. `DateResolver` (Task 4) implements this precisely.

## File Structure

```
civicpilot/
  __init__.py
  cache.py                          # Task 2
  crosswalk.py                      # Task 3
  date_resolver.py                  # Task 4
  data/
    agency_crosswalk.json           # Task 3
  clients/
    __init__.py
    fr_client.py                    # Task 5
    usaspending_client.py           # Task 7
    usaspending_download_client.py  # Task 8
  servers/
    __init__.py
    fr_server.py                    # Task 6
    usaspending_server.py           # Task 9
  agent/
    __init__.py
    llm_client.py                   # Task 10
    citation_guard.py                # Task 11
    orchestrator.py                  # Task 11
  main.py                            # Task 12
tests/
  test_cache.py                     # Task 2
  test_crosswalk.py                 # Task 3
  test_date_resolver.py             # Task 4
  test_fr_client.py                 # Task 5
  test_fr_server.py                 # Task 6
  test_usaspending_client.py        # Task 7
  test_usaspending_download_client.py # Task 8
  test_usaspending_server.py        # Task 9
  test_llm_client.py                # Task 10
  test_citation_guard.py            # Task 11
  test_orchestrator.py              # Task 11
  test_main.py                      # Task 12
  test_integration_end_to_end.py    # Task 12
pyproject.toml
.gitignore
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `civicpilot/__init__.py`, `civicpilot/clients/__init__.py`, `civicpilot/servers/__init__.py`, `civicpilot/agent/__init__.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Consumes: nothing
- Produces: an installable `civicpilot` package and a working `pytest` invocation for every later task to build on.

- [ ] **Step 1: Initialize git and create the directory skeleton**

```bash
git init
mkdir -p civicpilot/clients civicpilot/servers civicpilot/agent civicpilot/data tests
touch civicpilot/__init__.py civicpilot/clients/__init__.py civicpilot/servers/__init__.py civicpilot/agent/__init__.py tests/__init__.py
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "civicpilot"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "mcp>=1.0",
    "rapidfuzz>=3.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 3: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
civicpilot.egg-info/
```

- [ ] **Step 4: Install and verify pytest runs cleanly with zero tests**

```bash
pip install -e ".[dev]"
pytest
```

Expected: `pytest` reports "no tests ran" (or `0 collected`) with exit code 0 — no import errors.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore civicpilot tests
git commit -m "chore: scaffold civicpilot package"
```

---

### Task 2: Query cache

**Files:**
- Create: `civicpilot/cache.py`
- Test: `tests/test_cache.py`

**Interfaces:**
- Consumes: nothing
- Produces: `QueryCache(maxsize: int = 512, ttl_seconds: int = 300, clock: Callable[[], float] = time.monotonic)` with `.get(key: str) -> Any | None`, `.set(key: str, value: Any) -> None`, and static `QueryCache.make_key(*args, **kwargs) -> str`. Used by Tasks 5, 7.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cache.py
from civicpilot.cache import QueryCache


def test_set_and_get_roundtrip():
    cache = QueryCache()
    key = QueryCache.make_key("fr", "search", agency="epa")
    cache.set(key, {"count": 3})
    assert cache.get(key) == {"count": 3}


def test_missing_key_returns_none():
    cache = QueryCache()
    assert cache.get("nope") is None


def test_expired_entry_returns_none():
    fake_time = [0.0]
    cache = QueryCache(ttl_seconds=10, clock=lambda: fake_time[0])
    key = "k"
    cache.set(key, "v")
    fake_time[0] = 11.0
    assert cache.get(key) is None


def test_make_key_is_order_independent_for_kwargs():
    k1 = QueryCache.make_key("fr", agency="epa", type="rule")
    k2 = QueryCache.make_key("fr", type="rule", agency="epa")
    assert k1 == k2


def test_make_key_differs_for_different_args():
    k1 = QueryCache.make_key("fr", agency="epa")
    k2 = QueryCache.make_key("fr", agency="doe")
    assert k1 != k2


def test_set_evicts_oldest_entry_when_full():
    fake_time = [0.0]
    cache = QueryCache(maxsize=2, ttl_seconds=1000, clock=lambda: fake_time[0])
    cache.set("a", 1)
    fake_time[0] = 1.0
    cache.set("b", 2)
    fake_time[0] = 2.0
    cache.set("c", 3)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cache.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'civicpilot.cache'`.

- [ ] **Step 3: Implement `civicpilot/cache.py`**

```python
import hashlib
import json
import time
from typing import Any, Callable


class QueryCache:
    """In-process TTL cache keyed by normalized query parameters."""

    def __init__(
        self,
        maxsize: int = 512,
        ttl_seconds: int = 300,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._store: dict[str, tuple[float, Any]] = {}
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._clock = clock

    @staticmethod
    def make_key(*args: Any, **kwargs: Any) -> str:
        raw = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock() >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._store) >= self._maxsize and key not in self._store:
            oldest_key = min(self._store, key=lambda k: self._store[k][0])
            del self._store[oldest_key]
        self._store[key] = (self._clock() + self._ttl, value)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_cache.py -v
```

Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add civicpilot/cache.py tests/test_cache.py
git commit -m "feat: add in-process TTL query cache"
```

---

### Task 3: Agency crosswalk

**Files:**
- Create: `civicpilot/crosswalk.py`
- Create: `civicpilot/data/agency_crosswalk.json`
- Test: `tests/test_crosswalk.py`

**Interfaces:**
- Consumes: nothing
- Produces: `AgencyMapping(name, fr_slug, usaspending_toptier_code)`, `AgencyResolution(matched_name, fr_slug, usaspending_toptier_code, verified)`, `AgencyCrosswalk(mappings: list[AgencyMapping])` with `.resolve(agency_query: str) -> AgencyResolution`, and `load_default_crosswalk() -> AgencyCrosswalk`. Used by Task 11 (orchestrator).

- [ ] **Step 1: Write the seed crosswalk data**

```json
[
  {"name": "Environmental Protection Agency", "fr_slug": "environmental-protection-agency", "usaspending_toptier_code": "068"},
  {"name": "Department of Health and Human Services", "fr_slug": "health-and-human-services-department", "usaspending_toptier_code": "075"},
  {"name": "Department of Transportation", "fr_slug": "transportation-department", "usaspending_toptier_code": "069"},
  {"name": "Department of Defense", "fr_slug": "defense-department", "usaspending_toptier_code": "097"},
  {"name": "Department of Energy", "fr_slug": "energy-department", "usaspending_toptier_code": "089"},
  {"name": "Department of Homeland Security", "fr_slug": "homeland-security-department", "usaspending_toptier_code": "070"},
  {"name": "Department of Labor", "fr_slug": "labor-department", "usaspending_toptier_code": "016"},
  {"name": "Department of Education", "fr_slug": "education-department", "usaspending_toptier_code": "091"},
  {"name": "Department of Agriculture", "fr_slug": "agriculture-department", "usaspending_toptier_code": "012"},
  {"name": "Department of Justice", "fr_slug": "justice-department", "usaspending_toptier_code": "015"},
  {"name": "Department of the Treasury", "fr_slug": "treasury-department", "usaspending_toptier_code": "020"},
  {"name": "Department of Veterans Affairs", "fr_slug": "veterans-affairs-department", "usaspending_toptier_code": "036"}
]
```

Save this as `civicpilot/data/agency_crosswalk.json`. This is a starter set of 12 major agencies; the mechanism is designed to be extended with more entries over time as gaps are found in real usage — it does not need to reach the spec's eventual ~30-50 agencies to be complete for this plan.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_crosswalk.py
from civicpilot.crosswalk import AgencyCrosswalk, AgencyMapping, load_default_crosswalk


def make_epa_only():
    return AgencyCrosswalk([
        AgencyMapping("Environmental Protection Agency", "environmental-protection-agency", "068"),
    ])


def test_exact_match_is_verified():
    cw = make_epa_only()
    res = cw.resolve("Environmental Protection Agency")
    assert res.verified is True
    assert res.fr_slug == "environmental-protection-agency"
    assert res.usaspending_toptier_code == "068"


def test_exact_match_is_case_insensitive():
    cw = make_epa_only()
    res = cw.resolve("environmental protection agency")
    assert res.verified is True


def test_fuzzy_match_is_flagged_unverified():
    cw = make_epa_only()
    res = cw.resolve("Enviromental Protection Agncy")
    assert res.verified is False
    assert res.fr_slug == "environmental-protection-agency"


def test_no_match_returns_unresolved():
    cw = make_epa_only()
    res = cw.resolve("Ministry of Silly Walks")
    assert res.verified is False
    assert res.fr_slug is None
    assert res.usaspending_toptier_code is None


def test_load_default_crosswalk_resolves_epa():
    cw = load_default_crosswalk()
    res = cw.resolve("Environmental Protection Agency")
    assert res.verified is True
    assert res.usaspending_toptier_code == "068"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_crosswalk.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'civicpilot.crosswalk'`.

- [ ] **Step 4: Implement `civicpilot/crosswalk.py`**

```python
import json
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz, process

DEFAULT_CROSSWALK_PATH = Path(__file__).parent / "data" / "agency_crosswalk.json"
FUZZY_THRESHOLD = 85


@dataclass(frozen=True)
class AgencyMapping:
    name: str
    fr_slug: str
    usaspending_toptier_code: str


@dataclass(frozen=True)
class AgencyResolution:
    matched_name: str
    fr_slug: str | None
    usaspending_toptier_code: str | None
    verified: bool


class AgencyCrosswalk:
    def __init__(self, mappings: list[AgencyMapping]):
        self._by_name = {m.name.lower(): m for m in mappings}

    def resolve(self, agency_query: str) -> AgencyResolution:
        key = agency_query.strip().lower()
        exact = self._by_name.get(key)
        if exact is not None:
            return AgencyResolution(
                matched_name=exact.name,
                fr_slug=exact.fr_slug,
                usaspending_toptier_code=exact.usaspending_toptier_code,
                verified=True,
            )

        candidates = list(self._by_name.keys())
        best = process.extractOne(key, candidates, scorer=fuzz.WRatio) if candidates else None
        if best is None or best[1] < FUZZY_THRESHOLD:
            return AgencyResolution(
                matched_name=agency_query,
                fr_slug=None,
                usaspending_toptier_code=None,
                verified=False,
            )

        match = self._by_name[best[0]]
        return AgencyResolution(
            matched_name=match.name,
            fr_slug=match.fr_slug,
            usaspending_toptier_code=match.usaspending_toptier_code,
            verified=False,
        )


def load_default_crosswalk(path: Path = DEFAULT_CROSSWALK_PATH) -> AgencyCrosswalk:
    raw = json.loads(path.read_text())
    mappings = [AgencyMapping(**entry) for entry in raw]
    return AgencyCrosswalk(mappings)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_crosswalk.py -v
```

Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add civicpilot/crosswalk.py civicpilot/data/agency_crosswalk.json tests/test_crosswalk.py
git commit -m "feat: add agency crosswalk with fuzzy-fallback flagging"
```

---

### Task 4: Date resolver

**Files:**
- Create: `civicpilot/date_resolver.py`
- Test: `tests/test_date_resolver.py`

**Interfaces:**
- Consumes: nothing
- Produces: `DateRange(start: date, end: date)`, `DateResolution(period_label: str, calendar_range: DateRange, fiscal_range: DateRange, diverges: bool)`, `DateResolver()` with `.resolve(period: str, today: date) -> DateResolution` for `period in {"quarter", "year"}`. Used by Task 11 (orchestrator).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_date_resolver.py
from datetime import date

import pytest

from civicpilot.date_resolver import DateRange, DateResolver


def test_quarter_never_diverges_because_quarters_are_calendar_aligned():
    resolver = DateResolver()
    res = resolver.resolve("quarter", today=date(2026, 8, 13))
    assert res.diverges is False
    assert res.calendar_range == res.fiscal_range
    assert res.calendar_range == DateRange(date(2026, 7, 1), date(2026, 9, 30))


def test_quarter_range_at_year_boundary():
    resolver = DateResolver()
    res = resolver.resolve("quarter", today=date(2026, 1, 15))
    assert res.diverges is False
    assert res.calendar_range == DateRange(date(2026, 1, 1), date(2026, 3, 31))


def test_year_diverges_before_fiscal_year_rolls_over():
    resolver = DateResolver()
    res = resolver.resolve("year", today=date(2026, 8, 13))
    assert res.diverges is True
    assert res.calendar_range == DateRange(date(2026, 1, 1), date(2026, 12, 31))
    assert res.fiscal_range == DateRange(date(2025, 10, 1), date(2026, 9, 30))


def test_year_diverges_after_fiscal_year_rolls_over_in_october():
    resolver = DateResolver()
    res = resolver.resolve("year", today=date(2026, 11, 1))
    assert res.diverges is True
    assert res.fiscal_range == DateRange(date(2026, 10, 1), date(2027, 9, 30))


def test_unsupported_period_raises():
    resolver = DateResolver()
    with pytest.raises(ValueError, match="unsupported period"):
        resolver.resolve("fortnight", today=date(2026, 1, 1))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_date_resolver.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'civicpilot.date_resolver'`.

- [ ] **Step 3: Implement `civicpilot/date_resolver.py`**

```python
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date


@dataclass(frozen=True)
class DateResolution:
    period_label: str
    calendar_range: DateRange
    fiscal_range: DateRange
    diverges: bool


def _last_day_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _calendar_quarter_range(today: date) -> DateRange:
    quarter_index = (today.month - 1) // 3
    start_month = quarter_index * 3 + 1
    start = date(today.year, start_month, 1)
    end_month = start_month + 2
    end_year = today.year
    if end_month > 12:
        end_month -= 12
        end_year += 1
    end = _last_day_of_month(end_year, end_month)
    return DateRange(start, end)


def _calendar_year_range(today: date) -> DateRange:
    return DateRange(date(today.year, 1, 1), date(today.year, 12, 31))


def _fiscal_year_range(today: date) -> DateRange:
    if today.month >= 10:
        return DateRange(date(today.year, 10, 1), date(today.year + 1, 9, 30))
    return DateRange(date(today.year - 1, 10, 1), date(today.year, 9, 30))


class DateResolver:
    """Resolves relative date phrases ('this quarter', 'this year') against
    both calendar-date (Federal Register) and fiscal-year (USAspending)
    conventions, and flags when the two conventions actually produce
    different date ranges.

    Calendar quarters and federal fiscal quarters are the same 3-month
    windows (just numbered differently), so 'quarter' never diverges.
    Calendar year and fiscal year cover genuinely different 12-month
    windows, so 'year' always diverges.
    """

    def resolve(self, period: str, today: date) -> DateResolution:
        if period == "quarter":
            cal = _calendar_quarter_range(today)
            return DateResolution("quarter", cal, cal, diverges=False)
        if period == "year":
            cal = _calendar_year_range(today)
            fis = _fiscal_year_range(today)
            return DateResolution("year", cal, fis, diverges=(cal != fis))
        raise ValueError(f"unsupported period: {period!r}. Supported periods: 'quarter', 'year'.")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_date_resolver.py -v
```

Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add civicpilot/date_resolver.py tests/test_date_resolver.py
git commit -m "feat: add calendar/fiscal date resolver"
```

---

### Task 5: Federal Register API client

**Files:**
- Create: `civicpilot/clients/fr_client.py`
- Test: `tests/test_fr_client.py`

**Interfaces:**
- Consumes: `QueryCache` (Task 2)
- Produces: `FR_BASE_URL`, `FederalRegisterClient(http_client: httpx.AsyncClient, cache: QueryCache)` with `async .search_documents(*, agency_slug=None, doc_type=None, start_date=None, end_date=None, per_page=20) -> dict` and `async .get_document(document_number: str) -> dict`. Used by Task 6.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fr_client.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_fr_client.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'civicpilot.clients.fr_client'`.

- [ ] **Step 3: Implement `civicpilot/clients/fr_client.py`**

```python
import httpx

from ..cache import QueryCache

FR_BASE_URL = "https://www.federalregister.gov/api/v1"


class FederalRegisterClient:
    def __init__(self, http_client: httpx.AsyncClient, cache: QueryCache):
        self._http = http_client
        self._cache = cache

    async def search_documents(
        self,
        *,
        agency_slug: str | None = None,
        doc_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        per_page: int = 20,
    ) -> dict:
        cache_key = QueryCache.make_key(
            "fr.search", agency_slug=agency_slug, doc_type=doc_type,
            start_date=start_date, end_date=end_date, per_page=per_page,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        params: dict[str, object] = {"per_page": per_page}
        if agency_slug:
            params["conditions[agencies][]"] = agency_slug
        if doc_type:
            params["conditions[type][]"] = doc_type
        if start_date:
            params["conditions[publication_date][gte]"] = start_date
        if end_date:
            params["conditions[publication_date][lte]"] = end_date

        response = await self._http.get(f"{FR_BASE_URL}/documents.json", params=params)
        response.raise_for_status()
        result = response.json()
        self._cache.set(cache_key, result)
        return result

    async def get_document(self, document_number: str) -> dict:
        cache_key = QueryCache.make_key("fr.get", document_number=document_number)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        response = await self._http.get(f"{FR_BASE_URL}/documents/{document_number}.json")
        response.raise_for_status()
        result = response.json()
        self._cache.set(cache_key, result)
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_fr_client.py -v
```

Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add civicpilot/clients/fr_client.py tests/test_fr_client.py
git commit -m "feat: add Federal Register API client"
```

---

### Task 6: Federal Register MCP server

**Files:**
- Create: `civicpilot/servers/fr_server.py`
- Test: `tests/test_fr_server.py`

**Interfaces:**
- Consumes: `FederalRegisterClient` (Task 5)
- Produces: `build_fr_server(client: FederalRegisterClient) -> FastMCP`, where the returned server exposes a real MCP tool `search_documents` (actions: `search`, `get`) and also carries a plain-callable attribute `._search_documents_impl(action, agency_slug=None, doc_type=None, start_date=None, end_date=None, document_number=None) -> dict` for in-process invocation. Used by Task 11 (orchestrator) and Task 12 (entry point).

Scope note: this task implements the `search` and `get` actions only. The spec's `get_agency` and `search_comments` actions are not needed for the flagship query (agency resolution is handled entirely by the crosswalk, Task 3) and are deferred to a later plan.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fr_server.py
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
        agency_slug="epa", doc_type=None, start_date=None, end_date=None,
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_fr_server.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'civicpilot.servers.fr_server'`.

- [ ] **Step 3: Implement `civicpilot/servers/fr_server.py`**

```python
from mcp.server.fastmcp import FastMCP

from ..clients.fr_client import FederalRegisterClient


async def _search_documents_impl(
    client: FederalRegisterClient,
    *,
    action: str,
    agency_slug: str | None = None,
    doc_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    document_number: str | None = None,
) -> dict:
    if action == "search":
        return await client.search_documents(
            agency_slug=agency_slug, doc_type=doc_type,
            start_date=start_date, end_date=end_date,
        )
    if action == "get":
        if not document_number:
            raise ValueError("document_number is required for action='get'")
        return await client.get_document(document_number)
    raise ValueError(f"unsupported action: {action!r}. Supported actions: 'search', 'get'.")


def build_fr_server(client: FederalRegisterClient) -> FastMCP:
    server = FastMCP("federal-register")

    async def search_documents(
        action: str,
        agency_slug: str | None = None,
        doc_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        document_number: str | None = None,
    ) -> dict:
        """Search or fetch Federal Register documents. action: 'search' or 'get'."""
        return await _search_documents_impl(
            client, action=action, agency_slug=agency_slug, doc_type=doc_type,
            start_date=start_date, end_date=end_date, document_number=document_number,
        )

    server.tool()(search_documents)
    server._search_documents_impl = search_documents
    return server
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_fr_server.py -v
```

Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add civicpilot/servers/fr_server.py tests/test_fr_server.py
git commit -m "feat: add Federal Register MCP server"
```

---

### Task 7: USAspending sync API client

**Files:**
- Create: `civicpilot/clients/usaspending_client.py`
- Test: `tests/test_usaspending_client.py`

**Interfaces:**
- Consumes: `QueryCache` (Task 2)
- Produces: `USASPENDING_BASE_URL`, `USASpendingClient(http_client, cache)` with `async .search_awards(*, toptier_code, start_date, end_date, award_type_codes=None, limit=10) -> dict`, `async .get_award(award_id: str) -> dict`, `async .spending_by_agency(*, toptier_code, fiscal_year: int) -> dict`. Used by Task 9.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_usaspending_client.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_usaspending_client.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'civicpilot.clients.usaspending_client'`.

- [ ] **Step 3: Implement `civicpilot/clients/usaspending_client.py`**

```python
import httpx

from ..cache import QueryCache

USASPENDING_BASE_URL = "https://api.usaspending.gov/api/v2"


class USASpendingClient:
    def __init__(self, http_client: httpx.AsyncClient, cache: QueryCache):
        self._http = http_client
        self._cache = cache

    async def search_awards(
        self,
        *,
        toptier_code: str,
        start_date: str,
        end_date: str,
        award_type_codes: list[str] | None = None,
        limit: int = 10,
    ) -> dict:
        award_type_codes = award_type_codes or ["A", "B", "C", "D"]
        cache_key = QueryCache.make_key(
            "usaspending.search_awards", toptier_code=toptier_code,
            start_date=start_date, end_date=end_date,
            award_type_codes=award_type_codes, limit=limit,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        body = {
            "filters": {
                "agencies": [{"type": "awarding", "tier": "toptier", "toptier_code": toptier_code}],
                "time_period": [{"start_date": start_date, "end_date": end_date}],
                "award_type_codes": award_type_codes,
            },
            "fields": ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency"],
            "page": 1,
            "limit": limit,
        }
        response = await self._http.post(f"{USASPENDING_BASE_URL}/search/spending_by_award/", json=body)
        response.raise_for_status()
        result = response.json()
        self._cache.set(cache_key, result)
        return result

    async def get_award(self, award_id: str) -> dict:
        cache_key = QueryCache.make_key("usaspending.get_award", award_id=award_id)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        response = await self._http.get(f"{USASPENDING_BASE_URL}/awards/{award_id}/")
        response.raise_for_status()
        result = response.json()
        self._cache.set(cache_key, result)
        return result

    async def spending_by_agency(self, *, toptier_code: str, fiscal_year: int) -> dict:
        cache_key = QueryCache.make_key(
            "usaspending.spending_by_agency", toptier_code=toptier_code, fiscal_year=fiscal_year,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        response = await self._http.get(
            f"{USASPENDING_BASE_URL}/agency/{toptier_code}/awards/",
            params={"fiscal_year": fiscal_year},
        )
        response.raise_for_status()
        result = response.json()
        self._cache.set(cache_key, result)
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_usaspending_client.py -v
```

Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add civicpilot/clients/usaspending_client.py tests/test_usaspending_client.py
git commit -m "feat: add USAspending sync API client"
```

---

### Task 8: USAspending async download client

**Files:**
- Create: `civicpilot/clients/usaspending_download_client.py`
- Test: `tests/test_usaspending_download_client.py`

**Interfaces:**
- Consumes: nothing beyond `httpx.AsyncClient`
- Produces: `USASpendingDownloadClient(http_client)` with `async .submit_bulk_download(*, toptier_code, start_date, end_date) -> dict` (returns `{"file_name": ...}` from the live API) and `async .poll_status(file_name: str) -> dict` (returns `{"status": "running"|"finished"|"failed", ...}`). Used by Task 9.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_usaspending_download_client.py
import httpx
import pytest
import respx

from civicpilot.clients.usaspending_client import USASPENDING_BASE_URL
from civicpilot.clients.usaspending_download_client import USASpendingDownloadClient


@pytest.mark.asyncio
@respx.mock
async def test_submit_bulk_download_returns_file_name():
    respx.post(f"{USASPENDING_BASE_URL}/bulk_download/awards/").mock(
        return_value=httpx.Response(200, json={"file_name": "job-1", "status_url": "https://example/status"})
    )
    async with httpx.AsyncClient() as http:
        client = USASpendingDownloadClient(http)
        result = await client.submit_bulk_download(toptier_code="068", start_date="2026-01-01", end_date="2026-03-31")
    assert result["file_name"] == "job-1"


@pytest.mark.asyncio
@respx.mock
async def test_poll_status_returns_running():
    respx.get(f"{USASPENDING_BASE_URL}/download/status/").mock(
        return_value=httpx.Response(200, json={"status": "running"})
    )
    async with httpx.AsyncClient() as http:
        client = USASpendingDownloadClient(http)
        result = await client.poll_status("job-1")
    assert result["status"] == "running"


@pytest.mark.asyncio
@respx.mock
async def test_poll_status_returns_finished_with_file_url():
    respx.get(f"{USASPENDING_BASE_URL}/download/status/").mock(
        return_value=httpx.Response(200, json={"status": "finished", "file_url": "https://example/job-1.csv"})
    )
    async with httpx.AsyncClient() as http:
        client = USASpendingDownloadClient(http)
        result = await client.poll_status("job-1")
    assert result["file_url"] == "https://example/job-1.csv"


@pytest.mark.asyncio
@respx.mock
async def test_submit_bulk_download_raises_on_http_error():
    respx.post(f"{USASPENDING_BASE_URL}/bulk_download/awards/").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as http:
        client = USASpendingDownloadClient(http)
        with pytest.raises(httpx.HTTPStatusError):
            await client.submit_bulk_download(toptier_code="068", start_date="2026-01-01", end_date="2026-03-31")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_usaspending_download_client.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'civicpilot.clients.usaspending_download_client'`.

- [ ] **Step 3: Implement `civicpilot/clients/usaspending_download_client.py`**

```python
import httpx

from .usaspending_client import USASPENDING_BASE_URL


class USASpendingDownloadClient:
    def __init__(self, http_client: httpx.AsyncClient):
        self._http = http_client

    async def submit_bulk_download(self, *, toptier_code: str, start_date: str, end_date: str) -> dict:
        body = {
            "filters": {
                "agencies": [{"type": "awarding", "tier": "toptier", "toptier_code": toptier_code}],
                "time_period": [{"start_date": start_date, "end_date": end_date}],
            },
            "file_format": "csv",
        }
        response = await self._http.post(f"{USASPENDING_BASE_URL}/bulk_download/awards/", json=body)
        response.raise_for_status()
        return response.json()

    async def poll_status(self, file_name: str) -> dict:
        response = await self._http.get(
            f"{USASPENDING_BASE_URL}/download/status/", params={"file_name": file_name},
        )
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_usaspending_download_client.py -v
```

Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add civicpilot/clients/usaspending_download_client.py tests/test_usaspending_download_client.py
git commit -m "feat: add USAspending async bulk-download client"
```

---

### Task 9: USAspending MCP server

**Files:**
- Create: `civicpilot/servers/usaspending_server.py`
- Test: `tests/test_usaspending_server.py`

**Interfaces:**
- Consumes: `USASpendingClient` (Task 7), `USASpendingDownloadClient` (Task 8)
- Produces: `build_usaspending_server(client, download_client) -> FastMCP`, exposing three real MCP tools — `query_spending` (actions: `search_awards`, `get_award`, `spending_by_agency`), `submit_spending_query`, `get_spending_result` — plus in-process callable attributes `._query_spending_impl(action, toptier_code, start_date=None, end_date=None, award_id=None, fiscal_year=None) -> dict`, `._submit_spending_query_impl(...) -> dict`, `._get_spending_result_impl(job_id) -> dict`. Used by Task 11 and Task 12.

- [ ] **Step 1: Write the failing tests for `query_spending` dispatch**

```python
# tests/test_usaspending_server.py
from unittest.mock import AsyncMock

import pytest

from civicpilot.servers.usaspending_server import (
    MAX_POLL_WINDOW_SECONDS,
    _get_spending_result_impl,
    _query_spending_impl,
    _submit_spending_query_impl,
    build_usaspending_server,
)


@pytest.mark.asyncio
async def test_query_spending_search_awards_requires_dates():
    client = AsyncMock()
    with pytest.raises(ValueError, match="start_date and end_date are required"):
        await _query_spending_impl(client, action="search_awards", toptier_code="068")


@pytest.mark.asyncio
async def test_query_spending_dispatches_search_awards():
    client = AsyncMock()
    client.search_awards.return_value = {"results": []}
    result = await _query_spending_impl(
        client, action="search_awards", toptier_code="068",
        start_date="2026-01-01", end_date="2026-03-31",
    )
    assert result == {"results": []}


@pytest.mark.asyncio
async def test_query_spending_dispatches_get_award():
    client = AsyncMock()
    client.get_award.return_value = {"id": "AWD-1"}
    result = await _query_spending_impl(client, action="get_award", toptier_code="068", award_id="AWD-1")
    assert result == {"id": "AWD-1"}


@pytest.mark.asyncio
async def test_query_spending_dispatches_spending_by_agency():
    client = AsyncMock()
    client.spending_by_agency.return_value = {"total_obligations": 4200000}
    result = await _query_spending_impl(client, action="spending_by_agency", toptier_code="068", fiscal_year=2026)
    assert result == {"total_obligations": 4200000}


@pytest.mark.asyncio
async def test_query_spending_unsupported_action_raises():
    client = AsyncMock()
    with pytest.raises(ValueError, match="unsupported action"):
        await _query_spending_impl(client, action="delete_everything", toptier_code="068")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_usaspending_server.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'civicpilot.servers.usaspending_server'`.

- [ ] **Step 3: Implement the sync-dispatch half of `civicpilot/servers/usaspending_server.py`**

```python
import asyncio
import time

from mcp.server.fastmcp import FastMCP

from ..clients.usaspending_client import USASpendingClient
from ..clients.usaspending_download_client import USASpendingDownloadClient

MAX_POLL_WINDOW_SECONDS = 8
POLL_INTERVAL_SECONDS = 2


async def _query_spending_impl(
    client: USASpendingClient,
    *,
    action: str,
    toptier_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    award_id: str | None = None,
    fiscal_year: int | None = None,
) -> dict:
    if action == "search_awards":
        if not (start_date and end_date):
            raise ValueError("start_date and end_date are required for action='search_awards'")
        return await client.search_awards(toptier_code=toptier_code, start_date=start_date, end_date=end_date)
    if action == "get_award":
        if not award_id:
            raise ValueError("award_id is required for action='get_award'")
        return await client.get_award(award_id)
    if action == "spending_by_agency":
        if not fiscal_year:
            raise ValueError("fiscal_year is required for action='spending_by_agency'")
        return await client.spending_by_agency(toptier_code=toptier_code, fiscal_year=fiscal_year)
    raise ValueError(
        f"unsupported action: {action!r}. "
        "Supported actions: 'search_awards', 'get_award', 'spending_by_agency'."
    )
```

- [ ] **Step 4: Run the dispatch tests to verify they pass**

```bash
pytest tests/test_usaspending_server.py -v -k query_spending
```

Expected: PASS (5 tests). `submit`/`get_spending_result` tests still fail to collect — that's expected until Step 5.

- [ ] **Step 5: Write the failing tests for the async submit/poll pair**

Append to `tests/test_usaspending_server.py`:

```python
@pytest.mark.asyncio
async def test_submit_returns_complete_when_job_finishes_within_window():
    download_client = AsyncMock()
    download_client.submit_bulk_download.return_value = {"file_name": "job-1"}
    download_client.poll_status.return_value = {"status": "finished", "file_url": "https://example/job-1.csv"}

    fake_now = [0.0]

    async def fake_sleep(_):
        fake_now[0] += 2

    result = await _submit_spending_query_impl(
        download_client, toptier_code="068", start_date="2026-01-01", end_date="2026-03-31",
        sleep=fake_sleep, clock=lambda: fake_now[0],
    )
    assert result == {"status": "complete", "file_url": "https://example/job-1.csv", "job_id": "job-1"}


@pytest.mark.asyncio
async def test_submit_returns_pending_when_job_does_not_finish_within_window():
    download_client = AsyncMock()
    download_client.submit_bulk_download.return_value = {"file_name": "job-2"}
    download_client.poll_status.return_value = {"status": "running"}

    fake_now = [0.0]

    async def fake_sleep(_):
        fake_now[0] += 3

    result = await _submit_spending_query_impl(
        download_client, toptier_code="068", start_date="2026-01-01", end_date="2026-03-31",
        poll_window_seconds=MAX_POLL_WINDOW_SECONDS, poll_interval_seconds=3,
        sleep=fake_sleep, clock=lambda: fake_now[0],
    )
    assert result == {"status": "pending", "job_id": "job-2"}


@pytest.mark.asyncio
async def test_submit_returns_failed_status():
    download_client = AsyncMock()
    download_client.submit_bulk_download.return_value = {"file_name": "job-3"}
    download_client.poll_status.return_value = {"status": "failed", "message": "bad filters"}

    result = await _submit_spending_query_impl(
        download_client, toptier_code="068", start_date="2026-01-01", end_date="2026-03-31",
        sleep=AsyncMock(), clock=lambda: 0.0,
    )
    assert result == {"status": "failed", "job_id": "job-3", "message": "bad filters"}


@pytest.mark.asyncio
async def test_get_spending_result_returns_complete():
    download_client = AsyncMock()
    download_client.poll_status.return_value = {"status": "finished", "file_url": "https://example/job-4.csv"}
    result = await _get_spending_result_impl(download_client, job_id="job-4")
    assert result == {"status": "complete", "file_url": "https://example/job-4.csv", "job_id": "job-4"}


@pytest.mark.asyncio
async def test_get_spending_result_returns_pending():
    download_client = AsyncMock()
    download_client.poll_status.return_value = {"status": "running"}
    result = await _get_spending_result_impl(download_client, job_id="job-5")
    assert result == {"status": "pending", "job_id": "job-5"}
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
pytest tests/test_usaspending_server.py -v
```

Expected: FAIL — `_submit_spending_query_impl` and `_get_spending_result_impl` not defined.

- [ ] **Step 7: Implement the async half and the `build_usaspending_server` factory**

Append to `civicpilot/servers/usaspending_server.py`:

```python
async def _submit_spending_query_impl(
    download_client: USASpendingDownloadClient,
    *,
    toptier_code: str,
    start_date: str,
    end_date: str,
    poll_window_seconds: int = MAX_POLL_WINDOW_SECONDS,
    poll_interval_seconds: int = POLL_INTERVAL_SECONDS,
    sleep=asyncio.sleep,
    clock=time.monotonic,
) -> dict:
    submission = await download_client.submit_bulk_download(
        toptier_code=toptier_code, start_date=start_date, end_date=end_date,
    )
    file_name = submission["file_name"]
    deadline = clock() + poll_window_seconds
    while clock() < deadline:
        status = await download_client.poll_status(file_name)
        if status["status"] == "finished":
            return {"status": "complete", "file_url": status["file_url"], "job_id": file_name}
        if status["status"] == "failed":
            return {"status": "failed", "job_id": file_name, "message": status.get("message", "download failed")}
        await sleep(poll_interval_seconds)
    return {"status": "pending", "job_id": file_name}


async def _get_spending_result_impl(download_client: USASpendingDownloadClient, *, job_id: str) -> dict:
    status = await download_client.poll_status(job_id)
    if status["status"] == "finished":
        return {"status": "complete", "file_url": status["file_url"], "job_id": job_id}
    if status["status"] == "failed":
        return {"status": "failed", "job_id": job_id, "message": status.get("message", "download failed")}
    return {"status": "pending", "job_id": job_id}


def build_usaspending_server(
    client: USASpendingClient, download_client: USASpendingDownloadClient,
) -> FastMCP:
    server = FastMCP("usaspending")

    async def query_spending(
        action: str,
        toptier_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        award_id: str | None = None,
        fiscal_year: int | None = None,
    ) -> dict:
        """Query USAspending award data. action: 'search_awards', 'get_award', or 'spending_by_agency'."""
        return await _query_spending_impl(
            client, action=action, toptier_code=toptier_code, start_date=start_date,
            end_date=end_date, award_id=award_id, fiscal_year=fiscal_year,
        )

    async def submit_spending_query(toptier_code: str, start_date: str, end_date: str) -> dict:
        """Submit a bulk spending download; returns inline if it completes within ~8s, otherwise a job_id to poll."""
        return await _submit_spending_query_impl(
            download_client, toptier_code=toptier_code, start_date=start_date, end_date=end_date,
        )

    async def get_spending_result(job_id: str) -> dict:
        """Check the status of a previously submitted bulk spending download."""
        return await _get_spending_result_impl(download_client, job_id=job_id)

    server.tool()(query_spending)
    server.tool()(submit_spending_query)
    server.tool()(get_spending_result)
    server._query_spending_impl = query_spending
    server._submit_spending_query_impl = submit_spending_query
    server._get_spending_result_impl = get_spending_result
    return server
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
pytest tests/test_usaspending_server.py -v
```

Expected: PASS (10 tests).

- [ ] **Step 9: Commit**

```bash
git add civicpilot/servers/usaspending_server.py tests/test_usaspending_server.py
git commit -m "feat: add USAspending MCP server with hybrid async query pattern"
```

---

### Task 10: Groq LLM client

**Files:**
- Create: `civicpilot/agent/llm_client.py`
- Test: `tests/test_llm_client.py`

**Interfaces:**
- Consumes: nothing beyond `httpx.AsyncClient`
- Produces: `GROQ_BASE_URL`, `DEFAULT_MODEL = "moonshotai/kimi-k2-instruct"`, `GroqClient(http_client, api_key: str, model: str = DEFAULT_MODEL)` with `async .chat(messages: list[dict], tools: list[dict] | None = None) -> dict`. Used by Task 11, Task 12.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_client.py
import json

import httpx
import pytest
import respx

from civicpilot.agent.llm_client import DEFAULT_MODEL, GROQ_BASE_URL, GroqClient


@pytest.mark.asyncio
@respx.mock
async def test_chat_sends_model_and_messages_and_returns_parsed_response():
    route = respx.post(f"{GROQ_BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "hi"}}]})
    )
    async with httpx.AsyncClient() as http:
        client = GroqClient(http, api_key="test-key")
        result = await client.chat([{"role": "user", "content": "hello"}])
    assert result["choices"][0]["message"]["content"] == "hi"
    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body["model"] == DEFAULT_MODEL


@pytest.mark.asyncio
@respx.mock
async def test_chat_includes_tools_when_provided():
    route = respx.post(f"{GROQ_BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "tool_calls": []}}]})
    )
    tools = [{"type": "function", "function": {"name": "search_documents", "parameters": {}}}]
    async with httpx.AsyncClient() as http:
        client = GroqClient(http, api_key="test-key")
        await client.chat([{"role": "user", "content": "hello"}], tools=tools)
    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body["tools"] == tools


@pytest.mark.asyncio
@respx.mock
async def test_chat_sends_authorization_header():
    respx.post(f"{GROQ_BASE_URL}/chat/completions").mock(return_value=httpx.Response(200, json={"choices": []}))
    async with httpx.AsyncClient() as http:
        client = GroqClient(http, api_key="secret-123")
        await client.chat([{"role": "user", "content": "hi"}])
    request = respx.calls[0].request
    assert request.headers["Authorization"] == "Bearer secret-123"


@pytest.mark.asyncio
@respx.mock
async def test_chat_raises_on_http_error():
    respx.post(f"{GROQ_BASE_URL}/chat/completions").mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    async with httpx.AsyncClient() as http:
        client = GroqClient(http, api_key="bad")
        with pytest.raises(httpx.HTTPStatusError):
            await client.chat([{"role": "user", "content": "hi"}])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_llm_client.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'civicpilot.agent.llm_client'`.

- [ ] **Step 3: Implement `civicpilot/agent/llm_client.py`**

```python
import httpx

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "moonshotai/kimi-k2-instruct"


class GroqClient:
    def __init__(self, http_client: httpx.AsyncClient, api_key: str, model: str = DEFAULT_MODEL):
        self._http = http_client
        self._api_key = api_key
        self._model = model

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        body: dict[str, object] = {"model": self._model, "messages": messages}
        if tools:
            body["tools"] = tools
        response = await self._http.post(
            f"{GROQ_BASE_URL}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_llm_client.py -v
```

Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add civicpilot/agent/llm_client.py tests/test_llm_client.py
git commit -m "feat: add Groq (Kimi K2) LLM client"
```

---

### Task 11: Citation guard and orchestrator

**Files:**
- Create: `civicpilot/agent/citation_guard.py`
- Create: `civicpilot/agent/orchestrator.py`
- Test: `tests/test_citation_guard.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `GroqClient` (Task 10), `AgencyCrosswalk`/`AgencyResolution` (Task 3), `DateResolver`/`DateResolution` (Task 4), the `_search_documents_impl`-shaped and `_query_spending_impl`-shaped callables (Tasks 6, 9)
- Produces: `enforce_citations(answer_text: str) -> tuple[str, list[str]]`; `OrchestratorResult(answer, dropped_claims=[], needs_clarification=False, clarification_question=None)`; `MAX_TOOL_ITERATIONS`; `Orchestrator(llm, fr_impl, usaspending_impl, crosswalk, date_resolver)` with `async .handle_query(user_query: str, today: date | None = None) -> OrchestratorResult`. Used by Task 12.

- [ ] **Step 1: Write the failing tests for the citation guard**

```python
# tests/test_citation_guard.py
from civicpilot.agent.citation_guard import enforce_citations


def test_enforce_citations_keeps_cited_sentences():
    text = "The EPA proposed a new rule [doc:2026-12345] affecting emissions."
    kept, dropped = enforce_citations(text)
    assert "[doc:2026-12345]" in kept
    assert dropped == []


def test_enforce_citations_drops_uncited_factual_claims():
    text = (
        "The EPA proposed a new rule [doc:2026-12345]. "
        "The agency spent one billion dollars on enforcement this year."
    )
    kept, dropped = enforce_citations(text)
    assert "[doc:2026-12345]" in kept
    assert "one billion dollars" not in kept
    assert len(dropped) == 1


def test_enforce_citations_keeps_clarifying_questions():
    text = "Did you mean fiscal year 2026 or calendar year 2026?"
    kept, dropped = enforce_citations(text)
    assert kept == text
    assert dropped == []


def test_enforce_citations_keeps_short_lead_ins():
    text = "Here's a summary. EPA proposed a rule [doc:2026-1]."
    kept, dropped = enforce_citations(text)
    assert "Here's a summary." in kept
    assert "[doc:2026-1]" in kept
    assert dropped == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_citation_guard.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'civicpilot.agent.citation_guard'`.

- [ ] **Step 3: Implement `civicpilot/agent/citation_guard.py`**

```python
import re

CITATION_PATTERN = re.compile(r"\[(?:doc|award):[\w-]+\]")
SHORT_SENTENCE_THRESHOLD = 40


def enforce_citations(answer_text: str) -> tuple[str, list[str]]:
    """Splits the answer into sentences and keeps only those carrying a
    citation marker, plus clarifying questions and short connective
    lead-ins. Uncited factual-looking sentences are dropped rather than
    passed through, enforcing the groundedness guardrail at composition
    time rather than relying on prompting alone.
    """
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer_text.strip()) if s]
    kept: list[str] = []
    dropped: list[str] = []
    for sentence in sentences:
        if CITATION_PATTERN.search(sentence):
            kept.append(sentence)
        elif sentence.rstrip().endswith("?"):
            kept.append(sentence)
        elif len(sentence) < SHORT_SENTENCE_THRESHOLD:
            kept.append(sentence)
        else:
            dropped.append(sentence)
    return " ".join(kept), dropped
```

- [ ] **Step 4: Run citation guard tests to verify they pass**

```bash
pytest tests/test_citation_guard.py -v
```

Expected: PASS (4 tests).

- [ ] **Step 5: Commit the citation guard**

```bash
git add civicpilot/agent/citation_guard.py tests/test_citation_guard.py
git commit -m "feat: add citation enforcement guardrail"
```

- [ ] **Step 6: Write the failing tests for the orchestrator**

```python
# tests/test_orchestrator.py
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
    assert llm.chat.await_count == MAX_TOOL_ITERATIONS
```

- [ ] **Step 7: Run tests to verify they fail**

```bash
pytest tests/test_orchestrator.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'civicpilot.agent.orchestrator'`.

- [ ] **Step 8: Implement `civicpilot/agent/orchestrator.py`**

```python
import json
from dataclasses import dataclass, field
from datetime import date

from ..crosswalk import AgencyCrosswalk
from ..date_resolver import DateResolver
from .citation_guard import enforce_citations
from .llm_client import GroqClient

MAX_TOOL_ITERATIONS = 5

SYSTEM_PROMPT = (
    "You are CivicPilot, an assistant that answers questions about US federal "
    "rules and related government spending. Always call the provided tools to "
    "look up facts rather than relying on prior knowledge. When you give your "
    "final answer, cite every factual claim with the source's own identifier "
    "in square brackets, e.g. [doc:2026-12345] for a Federal Register document "
    "or [award:AWD-1] for a USAspending award. Never state a fact you cannot "
    "cite this way."
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
                "doc_type": {"type": "string", "enum": ["RULE", "PROPOSED_RULE"]},
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
                "action": {"type": "string", "enum": ["search_awards", "get_award", "spending_by_agency"]},
                "agency_name": {"type": "string", "description": "Plain-language agency name"},
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "award_id": {"type": "string"},
                "fiscal_year": {"type": "integer"},
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
            ("last quarter", "quarter"), ("last year", "year"),
        ):
            if phrase in lowered:
                resolution = self._date_resolver.resolve(period, today)
                if resolution.diverges:
                    return phrase, resolution
        return None

    async def _dispatch_tool_call(self, name: str, arguments: dict) -> dict:
        agency_name = arguments.get("agency_name")
        resolution = self._crosswalk.resolve(agency_name) if agency_name else None

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
            )
        else:
            raise ValueError(f"unknown tool: {name!r}")

        if resolution is not None and not resolution.verified:
            result = {**result, "agency_match_verified": False, "agency_match_used": resolution.matched_name}
        return result

    async def handle_query(self, user_query: str, today: date | None = None) -> OrchestratorResult:
        today = today or date.today()

        ambiguity = self._detect_ambiguous_period(user_query, today)
        if ambiguity is not None:
            phrase, resolution = ambiguity
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

        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ]
        tools = [FR_TOOL_SCHEMA, USASPENDING_TOOL_SCHEMA]

        for _ in range(MAX_TOOL_ITERATIONS):
            response = await self._llm.chat(messages, tools=tools)
            message = response["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                raw_answer = message.get("content") or ""
                filtered_answer, dropped = enforce_citations(raw_answer)
                return OrchestratorResult(answer=filtered_answer, dropped_claims=dropped)

            messages.append(message)
            for call in tool_calls:
                fn = call["function"]
                arguments = json.loads(fn["arguments"])
                try:
                    result = await self._dispatch_tool_call(fn["name"], arguments)
                    content = json.dumps(result)
                except ValueError as exc:
                    content = json.dumps({"error": str(exc)})
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})

        return OrchestratorResult(
            answer="",
            needs_clarification=True,
            clarification_question=(
                "I couldn't complete this query within the available tool-call budget "
                "— could you narrow it down?"
            ),
        )
```

- [ ] **Step 9: Run tests to verify they pass**

```bash
pytest tests/test_orchestrator.py -v
```

Expected: PASS (6 tests).

- [ ] **Step 10: Commit**

```bash
git add civicpilot/agent/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add orchestrator with elicitation, crosswalk resolution, and citation enforcement"
```

---

### Task 12: Entry point wiring and end-to-end integration test

**Files:**
- Create: `civicpilot/main.py`
- Test: `tests/test_main.py`
- Test: `tests/test_integration_end_to_end.py`

**Interfaces:**
- Consumes: everything from Tasks 2–11
- Produces: `civicpilot/main.py` with `async build_orchestrator() -> Orchestrator` and a `main()` CLI entry point. This is the final task in the plan — no later task depends on it.

- [ ] **Step 1: Write the failing smoke test for wiring**

```python
# tests/test_main.py
import pytest

from civicpilot.agent.orchestrator import Orchestrator
from civicpilot.main import build_orchestrator


@pytest.mark.asyncio
async def test_build_orchestrator_wires_all_components(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    orchestrator = await build_orchestrator()
    assert isinstance(orchestrator, Orchestrator)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_main.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'civicpilot.main'`.

- [ ] **Step 3: Implement `civicpilot/main.py`**

```python
import asyncio
import os

import httpx

from .agent.llm_client import GroqClient
from .agent.orchestrator import Orchestrator
from .cache import QueryCache
from .clients.fr_client import FederalRegisterClient
from .clients.usaspending_client import USASpendingClient
from .clients.usaspending_download_client import USASpendingDownloadClient
from .crosswalk import load_default_crosswalk
from .date_resolver import DateResolver
from .servers.fr_server import build_fr_server
from .servers.usaspending_server import build_usaspending_server


async def build_orchestrator() -> Orchestrator:
    http = httpx.AsyncClient(timeout=30.0)
    cache = QueryCache()

    fr_server = build_fr_server(FederalRegisterClient(http, cache))
    usaspending_server = build_usaspending_server(
        USASpendingClient(http, cache), USASpendingDownloadClient(http),
    )

    llm = GroqClient(http, api_key=os.environ["GROQ_API_KEY"])

    return Orchestrator(
        llm=llm,
        fr_impl=fr_server._search_documents_impl,
        usaspending_impl=usaspending_server._query_spending_impl,
        crosswalk=load_default_crosswalk(),
        date_resolver=DateResolver(),
    )


async def main() -> None:
    orchestrator = await build_orchestrator()
    query = input("Ask CivicPilot: ")
    result = await orchestrator.handle_query(query)
    if result.needs_clarification:
        print(result.clarification_question)
    else:
        print(result.answer)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_main.py -v
```

Expected: PASS (1 test).

- [ ] **Step 5: Write the failing end-to-end integration test**

```python
# tests/test_integration_end_to_end.py
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
    respx.get(f"{FR_BASE_URL}/documents.json").mock(
        return_value=httpx.Response(200, json={
            "count": 1,
            "results": [{"document_number": "2026-12345", "title": "Emissions Reporting Rule"}],
        })
    )
    respx.get(f"{USASPENDING_BASE_URL}/agency/068/awards/").mock(
        return_value=httpx.Response(200, json={"toptier_code": "068", "total_obligations": 4200000})
    )

    first_turn = {
        "choices": [{"message": {
            "role": "assistant",
            "tool_calls": [{
                "id": "call_fr",
                "function": {"name": "search_federal_register", "arguments": json.dumps({
                    "action": "search", "agency_name": "Environmental Protection Agency",
                    "doc_type": "PROPOSED_RULE", "start_date": "2026-07-01", "end_date": "2026-09-30",
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
```

- [ ] **Step 6: Run test to verify it fails first (sanity check on mocks)**

```bash
pytest tests/test_integration_end_to_end.py -v
```

Expected: this exercises only already-implemented code, so it should PASS immediately. If it fails, check the mocked Groq tool-call argument names against `FR_TOOL_SCHEMA`/`USASPENDING_TOOL_SCHEMA` in `orchestrator.py` for a mismatch before changing any implementation code.

- [ ] **Step 7: Run the full test suite**

```bash
pytest -v
```

Expected: PASS, all tests across every task (approximately 50 tests), zero network access.

- [ ] **Step 8: Commit**

```bash
git add civicpilot/main.py tests/test_main.py tests/test_integration_end_to_end.py
git commit -m "feat: wire entry point and add end-to-end flagship query test"
```

---

## Self-Review Notes

**Spec coverage:** Federal Register server (search/get actions — get_agency/search_comments explicitly deferred, not needed since crosswalk handles agency resolution), USAspending server (all three sync actions plus the hybrid async pair), crosswalk with fuzzy-fallback flagging, in-process TTL cache, fiscal/calendar date resolution (with a documented correction: quarters never diverge, years do — refines the spec's looser "check if this quarter/this year would differ" framing into what's actually true), elicitation on genuine divergence, citation/groundedness enforcement at composition time. RAG over Federal Register text, the fine-tuned router classifier, Langfuse/evals infrastructure, and deployment packaging are explicitly out of scope for this plan per the phase split agreed during brainstorming — they are separate follow-on plans.

**Type consistency:** Verified `FederalRegisterClient.search_documents`/`get_document` signatures match what `fr_server._search_documents_impl` calls; `USASpendingClient`'s three methods match what `usaspending_server._query_spending_impl` calls; `build_fr_server`/`build_usaspending_server`'s `._search_documents_impl`/`._query_spending_impl` attributes match the `fr_impl`/`usaspending_impl` callable signatures the `Orchestrator` invokes; `AgencyResolution` and `DateResolution` field names match their usage in `orchestrator.py`.

**No placeholders:** All steps contain complete, runnable code; no TBD/TODO markers; scope reductions (FR action subset, deferred phases) are explicit design decisions stated in prose, not hidden gaps.
