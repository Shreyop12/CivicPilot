# CivicPilot Frontend Design

**Date:** 2026-08-14
**Status:** Approved for planning

## Pitch

CivicPilot today is a CLI: `input()` → `orchestrator.handle_query()` → `print()`. This adds a real
frontend — an agency-centric dashboard (spending trend + recent rules) with a persistent chat panel
for grounded follow-up questions, backed by a new thin API layer. The existing backend
(`civicpilot/agent`, `civicpilot/clients`, `civicpilot/servers`, `crosswalk.py`, `date_resolver.py`)
is wrapped, not rewritten.

## Scope

**In scope (v1):**
- Agency picker → single-agency dashboard (spending-by-fiscal-year chart, last 3 FYs; final rules
  list, last 12 months)
- Persistent chat panel with real multi-turn memory, grounded in `Orchestrator.handle_query`
- FastAPI backend exposing the dashboard data and chat as REST endpoints
- React + Vite + Tailwind + shadcn/ui frontend, structured for a later production deploy (build
  step, env-based API base URL, CORS) — not deployed as part of this work
- Vitest/RTL component tests (frontend) + FastAPI endpoint tests (backend)

**Deferred (not v1):**
- Multi-agency overview grid (landing page shows one agency at a time, picked from the rail)
- Auth / multi-user accounts (no org/auth system configured; single-user local tool for now)
- Persistent conversation storage (in-memory only; lost on server restart)
- Proposed-rules (PRORULE) in the dashboard list — final rules only, matches the "rules vs. money
  spent" framing
- Actual hosting/deployment (structured to allow it later, not done now)

## Visual design

Established via the brainstorming visual-companion session (mockups in
`.superpowers/brainstorm/`, gitignored) — direction name: **Docket Ledger**.

**Rationale:** CivicPilot's entire value proposition is refusing to state a fact it can't cite —
`citation_guard.py` strips uncited claims, and `agency_match_verified: false` flags an unresolved
agency name rather than silently trusting a fuzzy match. The visual signature is built from that
mechanic directly rather than generic "government portal" decoration: every factual claim (chart
data, rule list rows, chat answers) renders as a monospace citation-stamp chip —
`[doc:2026-16627]` / `[award:068-FY2026]` — green-bordered when verified, amber-bordered
("UNVERIFIED MATCH") when `agency_match_verified` is false. This was deliberately chosen over the
more conventional "civic blue" government-dashboard palette (closer to how USAspending.gov itself
looks) to avoid being one more generic gov portal.

**Tokens:**
- Color: background `#F6F7F9` (paper, not cream), card `#FFFFFF`, ink/foreground `#12172B`,
  primary `#1D2A54` (federal ink navy), verified-stamp `#146C43`, unverified-stamp `#A15C07`,
  destructive `#B91C1C`, border/hairline `#DADFE7`, muted foreground `#5B6472`
- Type: **Newsreader** (serif, display — agency record headers only, used sparingly),
  **IBM Plex Sans** (UI/body), **IBM Plex Mono** (every figure, date, fiscal year, and citation
  stamp — ties the "ledger" concept directly to real tabular data)
- Layout: three-column desktop shell — agency rail (searchable list, toptier codes in mono) |
  main record (eyebrow + serif agency name + mono metadata line, spending chart, docket-style
  rules list) | persistent chat panel ("Inquiry Log," right-docked)
- Responsive: rail collapses to a top drawer below 1024px; chat panel becomes a bottom sheet
  toggle below 768px — standard collapse pattern, not a novel one, to keep this scoped

## Architecture

### Topology

New `frontend/` (React SPA) and `civicpilot/api/` (FastAPI) sit alongside the existing package.
`civicpilot/agent`, `civicpilot/clients`, `civicpilot/servers`, `crosswalk.py`, `date_resolver.py`
are unchanged except for one additive method on `AgencyCrosswalk` (below) and one additive
parameter on `Orchestrator.handle_query` (below).

### Components (frontend)

- **`AgencyRail`** — search-filtered list of agencies (client-side filter over one
  `GET /api/agencies` call), selecting an agency loads its dashboard and starts a fresh
  conversation
- **`AgencyRecord`** — record header, obligations-by-fiscal-year chart, recent-final-rules list;
  sourced entirely from `GET /api/agencies/{toptier_code}/dashboard` — no LLM call, no tokens
  spent rendering the dashboard
- **`InquiryPanel`** — persistent chat, `POST /api/chat`; renders citation stamps inline in answer
  text, a distinct "needs more detail" style for `needs_clarification` responses, and a muted
  "`N` unverifiable claims omitted" caption when `dropped_claims` is non-empty

### Backend additions

**`AgencyCrosswalk` (additive):** a `list_all() -> list[AgencyMapping]` method exposing the full
table for `GET /api/agencies` — no new fuzzy-search endpoint; the rail's ~30-50 agencies are small
enough to filter client-side.

**`Orchestrator.handle_query` (additive):** gains `history: list[dict] | None = None`. History is
*not* a replay of raw tool-call/tool-result messages from prior turns — it's compact
`{role: "user"|"assistant", content: str}` pairs of prior questions and their final cited answers
only. Each turn still runs its own fresh tool-calling loop (system prompt regenerated with the
current date, `history` inserted after it, then the new user message). This is a deliberate choice:
naively replaying full raw tool traces across turns would reintroduce the exact token-budget
pressure fixed earlier today (a single `search_federal_register` result already runs ~14KB) —
compounded across every turn of a conversation. Bounding replay to synthesized answers keeps
per-turn token cost close to today's single-query cost regardless of conversation depth.

**`civicpilot/api/` (new, FastAPI):**
- `GET /api/agencies` → `[{name, toptier_code, fr_slug}]` from `AgencyCrosswalk.list_all()`
- `GET /api/agencies/{toptier_code}/dashboard` → `{name, toptier_code, fr_slug, obligations: [{fiscal_year, amount}], rules: [{document_number, title, type, publication_date, html_url}]}` —
  calls `usaspending_impl(action="spending_by_agency", ...)` for the last 3 fiscal years and
  `fr_impl(action="search", doc_type="RULE", ...)` for the last 12 months directly (bypassing the
  LLM entirely — this is data the app already has, not something to ask a model to fetch)
- `POST /api/chat` → body `{conversation_id: str, message: str}` → wraps `handle_query`; an
  in-memory `dict[str, list[dict]]` on the FastAPI process maps `conversation_id` to history (no
  DB — out of scope per "Deferred"). Frontend mints a new `conversation_id` whenever the selected
  agency changes.
- CORS enabled for the Vite dev origin (and, later, whatever a production frontend origin turns
  out to be — left as an env var, not hardcoded)

## Error handling

- Dashboard fetch failure (upstream FR/USAspending outage) → inline error card with retry, not a
  page crash; the two data sources fail independently (a spending outage shouldn't blank the rules
  list or vice versa)
- Chat: Groq/OpenRouter rate-limit and failover are already handled server-side by
  `FailoverLLMClient` — invisible to the frontend. Only an error that survives both providers
  surfaces as a chat error bubble ("Something went wrong — try again")
- `needs_clarification: true` responses render as a distinct prompt style, not a normal answer
  bubble — it's a question back to the user, not a finding
- `dropped_claims` (non-empty) renders as a small muted caption under the answer — this is the
  groundedness guardrail visibly working, not an error to hide
- Empty agency data (zero obligations or zero rules in the window) gets explicit empty-state text,
  not a blank chart/list

## Interaction details

- **Partial fiscal year:** the current (in-progress) FY's bar in the obligations chart is visually
  distinguished (reduced opacity, as in the mockup) and labeled "(partial)" — it isn't a full-year
  figure and presenting it identically to closed years would misrepresent the trend.
- **Citation stamp clicks:** a `[doc:...]` stamp links out to that document's `html_url` (already
  present in the FR search result) in a new tab. A `[award:...]` stamp from `spending_by_agency`
  is *not* clickable — that endpoint returns an agency-level aggregate, not a per-award record with
  its own URL, so there's nothing to link to. It renders as a stamp without a hover/click affordance.

## Testing

- **Backend:** `tests/test_api.py`, FastAPI's `httpx` test client, following the existing
  respx/mocked-dependency patterns already used throughout `tests/`
- **Frontend:** Vitest + React Testing Library component tests for `AgencyRail`, `AgencyRecord`,
  `InquiryPanel` with mocked `fetch`
- **Manual verification:** a real pass driving the running app (`npm run dev` + `uvicorn`) against
  live Groq/FR/USAspending APIs before calling any phase done — matches how the two production
  bugs fixed earlier today were actually caught (live testing, not the mocked suite alone)

## Residual risks

- **In-memory conversation store** means any FastAPI restart drops all active conversations —
  acceptable for a local/single-instance v1, called out explicitly rather than silently assumed
  away
- **History-compaction tradeoff:** replaying only synthesized answers (not raw tool traces) means
  a follow-up like "show me the actual document you cited" can't be answered from history alone —
  the model would need to re-call the tool, which it can do (the citation ID is in the replayed
  answer text), but it's a real limitation worth knowing about rather than assuming multi-turn
  memory is free
- **Crosswalk list size**: `list_all()` returning the full table client-side-filtered is fine at
  ~30-50 agencies; if the crosswalk grows substantially this assumption should be revisited (not
  a v1 concern)

## Deferred scope (explicitly out of v1)

- Multi-agency overview grid
- Auth / multi-user accounts
- Persistent (non-in-memory) conversation storage
- Proposed rules (PRORULE) in the dashboard
- Actual deployment/hosting
