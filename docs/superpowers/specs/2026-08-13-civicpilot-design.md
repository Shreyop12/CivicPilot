# CivicPilot Design

**Date:** 2026-08-13
**Status:** Approved for planning

## Pitch

An agent that answers questions about US federal government activity — proposed rules, and the spending related to them — by orchestrating purpose-built MCP servers over messy public data. Example: *"What EPA rules were proposed this quarter, and what's the related spending?"*

This is a scoped-down revision of a broader 5-server, 6-source original plan. The original plan named data.gov (CKAN), Census, and GTFS transit as additional servers; those are cut from v1 (see "Deferred scope" below) because the flagship use case doesn't need them and each carries its own unscoped complexity (CKAN is a metadata catalog, not uniform data access; GTFS has no single national API and doesn't map onto an on-demand MCP tool model; Census needs geocoding infrastructure not otherwise required). Narrowing to two sources keeps the reconciliation problem (the actual hard part) tractable while still being real.

## Scope

**In scope (v1):** Federal Register + USAspending, single agent, single deployment.

**Deferred (not v1):** Census, data.gov/CKAN, GTFS, EPA/NOAA APIs. Revisit only after the 2-server loop is proven end-to-end.

## Architecture

### Topology

Single Render service, single process. The agent and both MCP servers run together, communicating over an in-process/stdio MCP transport rather than as separately deployed network services. Chosen specifically to fit the 512MB free-tier budget and avoid cold-start multiplication across multiple hosted services, while still exposing real MCP tool schemas.

### Components

- **`fr_server`** (MCP server): Federal Register access. Consolidated `search_documents` tool with an action-enum (`search`, `get`, `get_agency`, `search_comments`) rather than one tool per endpoint.
- **`usaspending_server`** (MCP server): USAspending access. Consolidated `query_spending` tool (actions: `search_awards`, `get_award`, `spending_by_agency`), plus a dedicated async pair: `submit_spending_query` / `get_spending_result` (see "Async spending queries" below).
- **`crosswalk`** (static data, not a server): hand-built agency-identifier mapping table, FR agency slug ↔ USAspending CGAC/toptier code, covering ~30-50 major agencies that show up in realistic queries. Loaded at startup. Extended over time as gaps are found in production use.
- **`cache`**: in-process TTL cache (SQLite or dict-backed) in front of both servers' outbound calls, keyed on normalized query parameters. Reduces latency on repeat queries and reduces risk of exhausting Census-style unauthenticated caps or re-triggering slow USAspending jobs.
- **`agent`**: orchestrates tool calls; runs the `router_classifier` before tool selection; handles date-basis elicitation; composes cited answers with the groundedness guardrail applied at composition time.
- **`router_classifier`**: small fine-tuned encoder (e.g. MiniLM-class model) predicting which server(s)/action(s) a query needs. Served as a local inference call, not a separate hosted dependency.

### Why not RAG-based tool selection for routing

With only two servers and consolidated action-enum tools, total tool count is small enough (roughly 4-8 tools) that retrieval-based tool selection isn't solving a real problem at this scale — a directly-prompted or classifier-routed approach is simpler and just as effective. RAG-based selection is kept as a second, honestly-scoped showcase applied to a different, real bottleneck: reranking retrieved Federal Register document chunks (see "RAG over Federal Register text" below), not choosing between servers.

## Data flow (worked example)

Query: *"What EPA rules were proposed this quarter, and what's the related spending?"*

1. **Classify.** `router_classifier` predicts `[fr_server.search_documents, usaspending_server.query_spending]` — both sources needed.
2. **Date resolution.** "This quarter" is ambiguous: Federal Register uses calendar dates, USAspending uses fiscal year (Oct-Sep). The agent checks whether the two interpretations would actually produce different results given today's date. If they diverge, it elicits clarification from the user (calendar quarter vs. fiscal quarter) before running either query. If they happen to agree, it proceeds and states the assumption made in the final answer.
3. **Agency resolution.** "EPA" is looked up in the static crosswalk table, resolving simultaneously to the FR slug (`environmental-protection-agency`) and the USAspending toptier code (`068`). If an agency isn't in the table, the agent falls back to fuzzy name matching — but the resulting match is explicitly flagged as unverified in the final answer rather than silently trusted. Fuzzy matching is never the primary path.
4. **Fetch FR side.** `fr_server.search_documents(agency=..., type=proposed_rule, date_range=...)`, cache-checked before any live call.
5. **Fetch spending side.** `usaspending_server.submit_spending_query(agency=..., fy=..., ...)`, cache-checked first (see "Async spending queries").
6. **Reconcile & answer.** The agent composes the answer with every factual claim traced to a specific FR document ID or USAspending award ID. Claims that can't be traced to a source ID are dropped or flagged, not asserted.
7. **Staleness note.** The answer states data recency per source rather than one blanket timestamp — FR: publication date of the latest indexed document; USAspending: acknowledged ~1-2 month reporting lag.

## Async spending queries

USAspending's award-search endpoints are effectively async (submit → poll → download), not simple request/response. The `usaspending_server` exposes a **hybrid pattern**:

- `submit_spending_query` polls internally for a short bounded window (~8-10s).
- If the job completes within the window, the result is returned inline — the common case for realistic bounded queries stays a single tool call.
- If not, the tool returns a structured `{status: "pending", job_id}` response, and the agent calls `get_spending_result(job_id)` on a short bounded retry (not indefinite).
- This pending/job_id/next-action shape follows the "actionable errors" tool-design principle rather than either blocking indefinitely or exposing raw job mechanics for every query.
- Must survive a Render free-tier cold start mid-poll: a restart during polling should surface as "try again," not hang.

## Fiscal-year / calendar-year handling

Relative date terms ("this quarter," "this year") are ambiguous across the two sources. The agent elicits clarification only when the two interpretations would actually diverge for the current date; otherwise it proceeds under the calendar-date interpretation and states that assumption in the answer. This is evaluated explicitly in the eval set (see below).

## Agency crosswalk

A hand-built static mapping table (FR agency slug ↔ USAspending CGAC/toptier code) for ~30-50 major agencies, shipped with the app and extended over time. Chosen over a live SAM.gov Federal Hierarchy API dependency (avoids a third API's auth/rate-limit/reconciliation surface) and over pure fuzzy matching (avoids silently wrong agency matches in a system whose core promise is grounded, citable answers). Fuzzy matching is retained only as a labeled fallback for agencies missing from the table.

## RAG over Federal Register text

Federal Register documents are chunked and embedded via hosted embeddings (HF/Jina — not local, to respect the 512MB budget) into Qdrant Cloud's free tier. Retrieval is hybrid (BM25/keyword + vector), with a cross-encoder reranker over top-k candidates before they enter the model's context. This is scoped specifically to *within-FR document retrieval quality* — finding the right rule text or comment — and is kept separate from the `router_classifier`'s server/action-selection job.

## Fine-tuning

The `router_classifier` is a small fine-tuned encoder (not a QLoRA/LoRA decoder fine-tune — the earlier plan conflated the two) predicting `{server(s), action}` from a query. Training data and eval data must not overlap:

- ~100 hand-authored queries (grounded in real pulled FR documents and USAspending records) held out purely for the end-to-end eval set — never used in classifier training.
- A separate pool of training queries for the classifier, which can include synthetically generated examples since classifier training doesn't require the same ground-truth rigor as the eval set.
- Report a before/after comparison against a zero-shot (prompted, unfine-tuned) routing baseline.

## Evals & guardrails

- ~100 gold Q&As, hand-authored from real Federal Register documents and USAspending records pulled during development. Covers single-source queries, both-source queries, and deliberately ambiguous-date queries that exercise the elicitation path.
- **Groundedness guardrail**: enforced at answer composition time (step 6 of the data flow) — every claim must resolve to a cited document/award ID, not checked only after the fact.
- **Eval-time groundedness check**: an LLM-judge pass verifying cited IDs actually support the claims made against them, not just that a citation is present.
- **Prompt-injection guardrail**: retrieved document/comment text is always treated as data in context, never as instructions. A subset of eval cases includes adversarial text embedded in a mock document to test this holds.
- Langfuse traces on every tool call, with a token/cost dashboard.

## Deployment stack

- Render: single service, agent + both MCP servers in-process.
- Orchestration LLM: Kimi K2 on Groq as primary, Qwen3 on Cerebras as fallback — both open-weight models on generous free tiers, chosen over Gemini Flash for quality. Kept on two distinct provider infras (not just two models behind one provider) so a Groq outage or rate-limit spike doesn't take down the whole system; explicit rate-limit-aware retry/backoff on the primary before failing over, not simply try-then-switch. Google AI Studio/Gemini is dropped as a dependency entirely.
- Qdrant Cloud free tier for Federal Register document vectors.
- Hosted embeddings (HF/Jina).
- Langfuse cloud free tier for tracing.
- In-process TTL cache (no Redis needed at this scale).
- Router classifier trained on Colab/Kaggle, served as a local inference call at runtime.

## Residual risks

- **Crosswalk coverage gap**: the ~30-50 hand-mapped agencies won't cover every query. The fuzzy-fallback-with-flag behavior is the safety valve; should be eval-tested with an agency deliberately excluded from the table.
- **Cold-start mid-poll**: the async spending pattern's bounded retry must tolerate a Render free-tier instance sleeping and restarting mid-poll.
- **Qdrant 1GB cap**: should hold with FR-only indexing (vs. the original multi-source corpus), but needs a rough document/token budget check during implementation rather than an assumption that it fits.
- **USAspending/Federal Register API changes**: no official SLA from either; the cache and bounded-retry patterns are the primary mitigation, not a guarantee.

## Deferred scope (explicitly out of v1)

- Census (demographic/geographic context) — needs geocoding/FIPS resolution not otherwise required.
- data.gov/CKAN — is a metadata catalog, not uniform data access; each dataset's actual retrieval mechanism is heterogeneous per hosting agency.
- GTFS transit — no single national API; static feeds are large bulk files, realtime feeds need continuous polling infrastructure; doesn't fit the on-demand MCP tool model and isn't related to the core rules+spending use case.
- EPA/NOAA APIs — named in the original data-source list but never scoped as servers.
