# Ghostwatch — Project Plan

> **Your agents say they're working. Ghostwatch makes sure they actually are.**

Team: **Jayden** (backend, SDK, demo agents) · **Adit** (frontend, dashboard, UX). Timebox: 48 hours from kickoff (T+0).

Source-of-truth hierarchy. When documents disagree, the higher one wins:
1. `contract/API_CONTRACT.md`: everything crossing the frontend/backend boundary
2. `PROJECT_PLAN.md` (this file): architecture, ownership, schedule
3. `docs/PRODUCT_SPEC.md`: the original product brief (intent and rationale)

---

## 1. Architecture

```
┌──────────────────────────┐        ┌────────────────────────────────────────────────┐
│ Developer's agent process│        │ Ghostwatch backend (FastAPI, Python 3.12)       │
│                          │  REST  │                                                 │
│  demo agents / user code │──────▶ │  api/v1  ──▶ services/                          │
│  + ghostwatch SDK        │ 🔑     │              ingest   (events → steps, status)  │
│    - execution/step ctx  │        │              traces   (tree, offsets)           │
│    - @tool decorator     │        │              anomaly  (deterministic rules)     │
│    - batching, fail-open │        │              investigate (facts → LLM → verify) │
│    - replay worker       │◀────── │              replay   (bundle, compare)         │
└──────────────────────────┘ claim  │              stats                              │
                                    │  providers/llm: base · fable · rule_based       │
                                    │  sweeper (asyncio task): stale → timed_out      │
                                    └───────────────┬─────────────────────────────────┘
                                                    │ SQLAlchemy 2.0 (sync) + Alembic
                                              ┌─────▼─────┐
                                              │ PostgreSQL │ (docker compose)
                                              └─────▲─────┘
┌──────────────────────────────────────────┐        │
│ Ghostwatch dashboard (Next.js, TS)        │  REST  │
│  TanStack Query ─▶ lib/api client ─┬─ live ───────┘
│                                    └─ mock (contract/fixtures)
└──────────────────────────────────────────┘
```

### Key design decisions (and why)

| Decision | Why |
|---|---|
| **Event-sourced ingestion.** An append-only `events` table; `steps` and execution status are derived from it. | The raw events are the evidence. Investigations and anomalies point back at immutable records, which is what makes "evidence-based" credible. Idempotent `(execution_id, seq)` makes SDK retries safe. |
| **No Redis, no Celery.** Investigations run in FastAPI `BackgroundTasks`; the stale sweeper is an asyncio loop started in the app lifespan. | The spec says to avoid unnecessary infrastructure. Investigation volume in a demo is tiny. A queue adds failure modes and buys nothing here. |
| **Sync SQLAlchemy + psycopg 3.** | Simpler to write and test correctly in 48 h. FastAPI runs sync endpoints in a threadpool, which is plenty for this load. |
| **Facts are deterministic; hypotheses come from the LLM and are verified.** | This is the product's core claim. The LLM never produces evidence. It only reasons over facts that code extracted, and backend code rejects any citation that doesn't exist. Only the deterministic signature matcher can mark a root cause `confirmed`. |
| **LLM behind a `LLMProvider` interface, with a `rule_based` provider as fallback.** | The model can be swapped later. The demo can't be killed by a network or API-key problem. The UI always shows truthfully which provider produced a report. |
| **Replay runs in the SDK worker, not the backend.** | The agent's code lives in the developer's process. The backend coordinates (bundle, claim, compare). In sandbox mode the SDK serves recorded tool/LLM outputs and never executes side-effecting tools. This enables the killer demo: fix a bug locally, replay against the exact recorded inputs, and watch it pass. |
| **Waterfall-first trace explorer** (Gantt rows indented by depth), with an expandable tree and a step inspector panel. | This is how serious APM tools (Honeycomb, Datadog, Sentry) show traces. A node graph reads as "AI-themed dashboard". React Flow is P2 at most. |
| **snake_case JSON end to end; fixtures shared in `contract/fixtures/`.** | Removes a whole class of integration bugs. The same fixtures drive Adit's mock mode and Jayden's conformance tests, so drift shows up on day 1, not at integration. |

---

## 2. Repository structure and ownership

```
ghostwatch/
├── CLAUDE.md                 shared  ← auto-loaded rules for both Claudes
├── PROJECT_PLAN.md           shared
├── CONTRIBUTING.md           shared
├── README.md                 shared  (setup + demo; finalised T+44)
├── .env.example              shared  (each owner edits only their section)
├── .github/
│   ├── CODEOWNERS            shared
│   └── workflows/ci.yml      shared  (backend job: Jayden, frontend job: Adit)
├── contract/                 SHARED — change only via contract PR approved by both
│   ├── API_CONTRACT.md
│   └── fixtures/             canonical example responses (one JSON file per endpoint)
├── docs/
│   ├── PRODUCT_SPEC.md
│   ├── API.md                Jayden (human-readable endpoint docs; FastAPI /docs is the live version)
│   ├── DEMO_SCRIPT.md        shared
│   └── prompts/              the kickoff prompts for each developer's Claude
├── docker-compose.yml        Jayden (postgres + optional backend service)
├── backend/                  JAYDEN
│   ├── pyproject.toml        (uv)
│   ├── alembic/ , alembic.ini
│   ├── app/
│   │   ├── main.py           app factory, CORS, error handlers, lifespan (sweeper)
│   │   ├── config.py         pydantic-settings
│   │   ├── db.py
│   │   ├── ids.py            prefixed id generation
│   │   ├── models/           SQLAlchemy ORM
│   │   ├── schemas/          Pydantic models mirroring the contract 1:1
│   │   ├── api/v1/           routers: agents, executions, events, traces, stats, anomalies, investigations, replays, health
│   │   ├── services/
│   │   │   ├── ingest.py
│   │   │   ├── traces.py
│   │   │   ├── stats.py
│   │   │   ├── anomaly/      rules.py, baseline.py, engine.py, thresholds.py
│   │   │   ├── investigation/ facts.py, signatures.py, engine.py, verify.py, prompts.py
│   │   │   ├── replay.py     bundle, compare
│   │   │   └── pricing.py    model → $/token table (null if unknown)
│   │   ├── providers/llm/    base.py, fable.py, rule_based.py
│   │   └── sweeper.py
│   ├── tests/
│   └── PROGRESS.md           Jayden's Claude's state file
├── sdk/python/               JAYDEN
│   ├── pyproject.toml
│   └── ghostwatch/           __init__.py, client.py, execution.py, tools.py, replay.py, worker.py
├── demo/                     JAYDEN
│   ├── agents/               research_assistant.py, invoice_processor.py, support_triage.py
│   ├── fake_services/        deterministic fake search API / invoice API (no real network)
│   ├── seed.py               generates history by RUNNING the agents through the SDK
│   └── run_scenario.py       one command per demo step
└── frontend/                 ADIT
    ├── package.json
    ├── app/                  App Router routes (see §6)
    ├── components/
    │   ├── ui/               shadcn primitives
    │   ├── shell/            sidebar, header, command bar
    │   ├── data/             StatusBadge, SeverityBadge, Duration, Timestamp, IdChip, JsonViewer, DataTable, EmptyState, ErrorState
    │   ├── trace/            Waterfall, TraceTree, StepInspector
    │   ├── investigation/    FactList, HypothesisCard, RootCauseBanner, EvidenceItem
    │   └── replay/           ReplayDialog, ComparisonView
    ├── lib/api/              types.ts (mirrors contract), client.ts, live.ts, mock.ts, hooks.ts
    ├── mocks/fixtures/       synced copy of contract/fixtures (script: npm run sync-fixtures)
    ├── tests/
    └── PROGRESS.md           Adit's Claude's state file
```

**Hard rule:** Jayden's Claude writes only in `backend/`, `sdk/`, `demo/`, `docker-compose.yml`, `docs/API.md`, its own section of `.env.example` and the backend CI job. Adit's Claude writes only in `frontend/`, its own section of `.env.example` and the frontend CI job. `contract/` and the root docs change only through a dedicated PR approved by both humans.

---

## 3. Database schema (PostgreSQL, owned by Jayden, Alembic-managed)

All `id` columns are `TEXT` prefixed ids. All timestamps are `TIMESTAMPTZ` stored in UTC. Payloads are `JSONB`.

```sql
agents (
  id TEXT PK, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL, description TEXT,
  framework TEXT, metadata JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL
)

executions (
  id TEXT PK, agent_id TEXT FK→agents NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running','completed','failed','timed_out')),
  started_at TIMESTAMPTZ NOT NULL, ended_at TIMESTAMPTZ, duration_ms INT,
  last_event_at TIMESTAMPTZ NOT NULL,          -- for stale sweeper
  input JSONB, output JSONB, config JSONB NOT NULL DEFAULT '{}',
  error JSONB, tokens_input INT, tokens_output INT, cost_usd NUMERIC(12,6),
  step_count INT NOT NULL DEFAULT 0, tags TEXT[] NOT NULL DEFAULT '{}',
  replay_of TEXT FK→executions NULL, replay_id TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL
)
  INDEX (agent_id, started_at DESC), INDEX (status), INDEX (replay_of)

events (                                        -- append-only, never updated
  id TEXT PK, execution_id TEXT FK→executions NOT NULL, seq INT NOT NULL,
  type TEXT NOT NULL, timestamp TIMESTAMPTZ NOT NULL, received_at TIMESTAMPTZ NOT NULL,
  payload JSONB NOT NULL,
  UNIQUE (execution_id, seq)
)

steps (                                         -- derived from events
  id TEXT PK, execution_id TEXT FK→executions NOT NULL, parent_step_id TEXT NULL,
  ordinal INT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL, status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL, ended_at TIMESTAMPTZ, duration_ms INT,
  input JSONB, output JSONB, error JSONB, tool_name TEXT, model TEXT,
  tokens_input INT, tokens_output INT, attempt INT NOT NULL DEFAULT 1,
  metadata JSONB NOT NULL DEFAULT '{}',
  UNIQUE (execution_id, ordinal)
)
  INDEX (execution_id), INDEX (tool_name)

anomalies (
  id TEXT PK, agent_id TEXT FK NOT NULL, execution_id TEXT FK NULL,
  type TEXT NOT NULL, severity TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
  rule_id TEXT NOT NULL, title TEXT NOT NULL, explanation TEXT NOT NULL,
  evidence JSONB NOT NULL, detected_at TIMESTAMPTZ NOT NULL,
  UNIQUE (execution_id, type)                   -- re-running rules is idempotent
)

investigations (
  id TEXT PK, execution_id TEXT FK NOT NULL, status TEXT NOT NULL, trigger TEXT NOT NULL,
  provider TEXT NOT NULL, model TEXT, report JSONB, error JSONB,
  llm_raw_response JSONB,                        -- kept for audit/debug; never sent to frontend
  created_at TIMESTAMPTZ NOT NULL, completed_at TIMESTAMPTZ
)

replays (
  id TEXT PK, original_execution_id TEXT FK NOT NULL, replay_execution_id TEXT FK NULL,
  mode TEXT NOT NULL, status TEXT NOT NULL, side_effects_authorized BOOLEAN NOT NULL DEFAULT FALSE,
  note TEXT, error JSONB, comparison JSONB,
  requested_at TIMESTAMPTZ NOT NULL, claimed_at TIMESTAMPTZ, completed_at TIMESTAMPTZ
)
```

---

## 4. Investigation pipeline (backend, B9)

```
trace ──▶ facts.py (deterministic)          ──▶ signatures.py (deterministic)
          F1 "Step 5 parse_results failed       "missing_key_in_upstream_output":
              with KeyError: 'results'"          error is KeyError(k) AND the nearest
          F2 "Step 4 web_search output keys:     preceding tool output lacks key k
              ['data','meta']"                   → root_cause.status = confirmed
          F3 "web_search attempt 1 returned
              HTTP 200"  …                     ──▶ provider.investigate(facts, trace digest)
                                                    Fable via forced tool-use / structured
                                                    output → hypotheses, recommendations
                                               ──▶ verify.py: drop bad citations,
                                                    downgrade "confirmed", fill evidence_gaps
                                               ──▶ persist report
```

MVP signature set (each one a small pure function with a unit test): `missing_key_in_upstream_output`, `tool_http_error` (tool step output or error contains status ≥ 400 and a downstream step failed), `timeout_in_step` (execution timed out while a step was running), `retry_exhaustion` (final attempt of a retried step failed), `ghost_completion` (from the anomaly). Facts to always extract when present: the failing step and its error, the preceding 3 steps' outputs (excerpted), the retry history, every anomaly on the execution with its evidence, and how the execution compares to baseline (duration, tokens, step count).

The LLM receives facts (with ids) plus a compact trace digest (step list with truncated I/O, not the raw 64 KB payloads). It must return JSON matching the hypothesis/recommendation schema and may only cite `F*` ids and step ids it was given.

---

## 5. SDK and demo (backend side, B10/B11/B13)

```python
import ghostwatch as gw

gw.init(api_url="http://localhost:8000/api/v1", api_key=..., agent=gw.Agent(slug="research-assistant", name="Research Assistant"))

@gw.tool(side_effects=False)
def web_search(query: str) -> dict: ...

@gw.tool(side_effects=True)          # never runs in sandbox replay
def submit_invoice(invoice: dict) -> dict: ...

with gw.execution(input={"question": q}, config={"model": "claude-fable-5-2", "expected_steps": ["web_search", "summarize"]}) as run:
    with run.step("plan", type="reasoning") as s:
        s.output = {...}
    results = web_search(q)          # auto-recorded as a tool_call step, retries tracked via attempt
```

SDK requirements: background-thread batching (flush every 500 ms or 50 events, and on exit); **fail-open** (if Ghostwatch is unreachable, the host agent must never crash; log a warning and drop or buffer); exceptions inside `execution`/`step` contexts are recorded as `step.failed` / `execution.failed` and then re-raised.

**Demo agents** use `demo/fake_services/` (deterministic local fakes, no internet), so the demo is 100 % repeatable:

| Agent | Normal behaviour | Injected scenario |
|---|---|---|
| `research-assistant` | plan → web_search → parse_results → summarize (LLM, recorded/fake) → output | **Schema change**: fake search API returns `{"data": [...], "meta": {...}}` instead of `{"results": [...]}` → `parse_results` raises `KeyError: 'results'`. Signature `missing_key_in_upstream_output` → **confirmed**. Fix: parser accepts both shapes → sandbox replay → outcome `fixed`. |
| `invoice-processor` | extract_fields → validate → submit_invoice → output | **Ghost completion**: the validate step swallows an error and the agent reports success without ever calling `submit_invoice` (`expected_steps` includes it) → `ghost_completion` (critical). This is the tagline in action. |
| `support-triage` | classify → retrieve_kb → draft_reply | **Rate limiting**: kb tool returns 429 twice and then succeeds → `excessive_retries`; one slow run → `duration_spike`. |

`demo/seed.py` builds history by actually running these agents through the SDK against the live API (about 25 healthy runs each for baselines, then the scenarios). No direct DB inserts. Traces must come from real events.

---

## 6. Frontend routes (Adit)

| Route | Purpose |
|---|---|
| `/` | Overview: stat tiles, execution trend (stacked completed/failed/timed_out), agent health list, recent executions, open anomalies |
| `/agents`, `/agents/[id]` | Agent table with health and success rate; agent detail with its trend, executions and anomalies |
| `/executions` | Filterable, URL-synced table (agent, status, date range, duration, has anomaly, replay) |
| `/executions/[id]` | **Trace explorer**: header (status, duration, tokens, cost, replay lineage) · waterfall + tree · step inspector (input/output/error JSON, metadata) · anomalies strip · "Investigate" and "Replay" actions · raw events tab |
| `/traces` | Jump to a trace by id plus recent traces (links to `/executions/[id]`) |
| `/anomalies` | Anomaly feed grouped by severity, with evidence expanded inline and links to steps |
| `/investigations`, `/investigations/[executionId]` | Report view: root-cause banner (confirmed / probable / insufficient evidence, visually distinct) · **Facts** (with evidence chips → steps) · **Hypotheses** (confidence, cited facts) · **Recommendations** · evidence gaps · provider and model badge |
| `/replays`, `/replays/[id]` | Replay list; comparison view: side-by-side summaries, outcome badge, aligned step diff |
| `/settings` | API base URL, data mode (mock/live), health and LLM provider status from `/health` |

---

## 7. GitHub issues (create these at T+0; labels in brackets)

| ID | Title | Owner | Pri | Depends on |
|---|---|---|---|---|
| X0 | Bootstrap repo: commit kit files, CODEOWNERS, branches, labels, issues | Jayden (human) | P0 | — |
| X1 | Contract fixtures for every endpoint in `contract/fixtures/` [integration] | Adit | P0 | X0 |
| B1 | FastAPI skeleton: config, error envelope, CORS, `/health`, docker-compose postgres, `.github/workflows/ci.yml` with the backend job and an empty `frontend` job stub for Adit to fill [backend] | Jayden | P0 | X0 |
| B2 | ORM models + Alembic migration for full schema [backend] | Jayden | P0 | B1 |
| B3 | Agents API (upsert by slug, list with stats/health, get) [backend] | Jayden | P0 | B2 |
| B4 | Executions create/list(filters, pagination, sort)/detail [backend] | Jayden | P0 | B2 |
| B5 | Event ingestion → steps, status, idempotency, truncation, totals [backend] | Jayden | P0 | B4 |
| B6 | Trace + raw events endpoints (depth, offset_ms) [backend] | Jayden | P0 | B5 |
| B7 | Stats overview + timeseries (zero-filled buckets) [backend] | Jayden | P0 | B4 |
| B15 | Contract conformance tests: every fixture validates against Pydantic schemas; responses match [backend][integration] | Jayden | P0 | X1, B3–B7 |
| B10 | SDK core: init, execution/step contexts, @tool, batching, fail-open [backend] | Jayden | P0* | B5 |
| B8 | Anomaly engine: 8 rules, baselines, run on finalize, sweeper [backend] | Jayden | P0 | B5 |
| B11 | Demo agents + fake services + seed + scenario runner [backend] | Jayden | P0 | B10 |
| B9 | Investigation engine: facts, signatures, provider interface, rule_based + Fable providers, verify [backend] | Jayden | P0 | B6, B8 |
| B16 | `docs/API.md` + FastAPI OpenAPI descriptions [documentation] | Jayden | P0 | B9 |
| B12 | Replay API: create, claim + bundle, comparison [backend] | Jayden | P1 | B6 |
| B13 | SDK sandbox replay + worker command [backend] | Jayden | P1 | B10, B12 |
| B14 | Token totals + cost via pricing table [backend] | Jayden | P1 | B5 |
| F1 | Next.js scaffold, Tailwind, shadcn, design tokens, fonts, app shell + nav [frontend] | Adit | P0 | X0 |
| F2 | API layer: types.ts, mock adapter on fixtures, live adapter, TanStack hooks, mode switch [frontend] | Adit | P0 | X1, F1 |
| F3 | Data components: badges, Duration, Timestamp, IdChip, JsonViewer, DataTable, Empty/Error/Loading states [frontend] | Adit | P0 | F1 |
| F6 | **Trace explorer**: waterfall, tree, step inspector, raw events tab [frontend] | Adit | P0 | F2, F3 |
| F4 | Overview page [frontend] | Adit | P0 | F2, F3 |
| F5 | Executions table + URL-synced filters [frontend] | Adit | P0 | F2, F3 |
| F7 | Agents list + detail [frontend] | Adit | P0 | F2, F3 |
| F8 | Anomalies page [frontend] | Adit | P0 | F2, F3 |
| F9 | Investigations list + report view + trigger/poll from trace page [frontend] | Adit | P0 | F6 |
| F12 | Live integration pass: switch to live per page, fix contract mismatches, polling [integration] | Adit | P0 | SYNC 1/2 |
| F13 | Tests: Vitest for components and the API layer; Playwright smoke of the demo path [frontend] | Adit | P0 | F6, F9 |
| F10 | Replay dialog (side-effect authorization), list, comparison view [frontend] | Adit | P1 | F6 |
| F11 | Settings page [frontend] | Adit | P1 | F2 |
| X2 | SYNC 1 integration (T+12) [integration] | both | P0 | B3–B7, F4–F6 |
| X3 | SYNC 2 full P0 integration + demo dry run (T+29) [integration] | both | P0 | B8–B11, F7–F9 |
| X4 | README, DEMO_SCRIPT, rehearsal ×3, backup recording [documentation] | both | P0 | X3 |

\*The SDK is P1 in the product spec, but a thin SDK is needed to generate real traces for the demo and the seed data, so its core is treated as P0.

### Dependency map (what runs in parallel)

```
T+0  X0 ─┬─▶ B1 ─▶ B2 ─┬─▶ B3 ─┐
         │             ├─▶ B4 ─▶ B5 ─┬─▶ B6 ─┐
         │             │             ├─▶ B7  ├─▶ B9 ─▶ B16
         │             │             ├─▶ B8 ─┘
         │             │             └─▶ B10 ─▶ B11 ─▶ (seed data for SYNC 2)
         │             └─────────── B15 (continuous, needs X1)
         │
         └─▶ F1 ─▶ X1 ─▶ F2 ─┬─▶ F3 ─▶ F6 ─▶ F9
                             ├─▶ F4, F5, F7, F8      (parallel, all on mocks)
                             └─▶ F11
     Frontend never waits for the backend until SYNC 1. Backend never waits for the frontend.
```

---

## 8. 48-hour schedule

| Window | Jayden (backend) | Adit (frontend) | Gate |
|---|---|---|---|
| T+0 – 1 | X0 bootstrap; B1 | F1 scaffold + shell | Repo has kit files, branches, issues |
| T+1 – 3 | B2 schema/migration | X1 fixtures PR (Jayden reviews within 30 min) | Fixtures merged to main |
| T+3 – 12 | B3, B4, B5, B6, B7, B15 | F2, F3, **F6**, F4, F5 (all mock) | — |
| **T+12** | **SYNC 1** (1 h): Adit flips agents/executions/trace/stats to live against Jayden's branch; mismatches → fix on the owning side or contract PR | | Trace explorer renders a real trace |
| T+13 – 19 | Sleep | Sleep | — |
| T+19 – 29 | B10, B8, B11, B9 | F7, F8, F9, F12, F13 | — |
| **T+29** | **SYNC 2** (1.5 h): merge both branches to main; `seed.py`; run the full demo script end to end | | **P0 complete.** If not, cut P1 to the minimum and fix P0 only. |
| T+30 – 36 | B12, B13, B14, B16 | F10, F11, polish pass | — |
| T+36 – 40 | Sleep | Sleep | — |
| T+40 – 45 | Bug bash together, tests green, README, demo hardening | | `main` is demo-ready |
| T+45 – 48 | Rehearse ×3, record a backup video, buffer | | Ship |

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Contract drift between two independent Claudes | Frozen contract + shared fixtures + B15 conformance tests + contract-change PR process. Neither Claude edits `contract/` on its own. |
| Both editing the same files | Directory ownership + CODEOWNERS; root files change only via shared PRs; separate lockfiles per directory. |
| Migration conflicts | Only Jayden creates Alembic migrations. |
| LLM nondeterminism or outage during the demo | `rule_based` fallback; reports persisted, so the demo shows a stored report and can regenerate live as a bonus; fake services for every tool. |
| Fable API cost or rate limits | Investigations are only auto-triggered on failure or high anomalies; `force` is needed to regenerate; compact trace digest instead of raw payloads. |
| Replay complexity eats the schedule | P1, starting T+30. Minimum viable version = sandbox only, comparison by (ordinal, name). |
| Event ordering / clock skew | Ordering by `seq`, not timestamp; `offset_ms` computed server-side. |
| Huge payloads freeze the UI | 64 KB truncation marker; virtualised JSON viewer for large objects. |
| Timestamp and timezone bugs | UTC `Z` everywhere; the frontend formats locally for display only. |
| Scope creep from "one more feature" | Section 11 of the product spec: finish P0 before P1. Any new idea goes in an issue labelled P2. |
| Demo machine setup fails | `docker compose up` + `uv run` + `npm run dev`; README tested on a clean clone at T+44. |

---

## 10. Definition of done (MVP)

- [ ] `docker compose up -d && cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app` works from a clean clone; `cd frontend && npm i && npm run dev` works.
- [ ] Every contract endpoint is implemented and passes conformance tests; `/docs` lists them all.
- [ ] `demo/seed.py` produces history via the SDK; every trace in the UI comes from stored events.
- [ ] All 8 anomaly rules implemented with unit tests (one firing and one non-firing case each).
- [ ] Investigation on the schema-change scenario yields a **confirmed** root cause with evidence linking to the exact steps; on a scenario without a matching signature it yields `probable` or `insufficient_evidence`. Works with `LLM_PROVIDER=rule_based` and no network.
- [ ] Sandbox replay of the fixed research agent produces outcome `fixed`; live mode without authorization is refused.
- [ ] Every page has loading, empty and error states; no page shows fabricated numbers; unimplemented features are labelled "Not implemented" rather than faked.
- [ ] Backend tests and frontend tests pass in CI on `main`.
- [ ] `docs/DEMO_SCRIPT.md` run end to end 3 times without intervention.
- [ ] No secrets in git history.

---

## 11. Demo script (summary; full version in `docs/DEMO_SCRIPT.md`)

1. Overview: three agents, real history, one degraded.
2. `run_scenario.py healthy research-assistant` → open the trace → walk the waterfall.
3. `run_scenario.py schema-change` → execution fails → anomaly + auto investigation appear.
4. Investigation: **Confirmed** banner → facts F1/F2 → click evidence → jumps to the step with the `KeyError` and the upstream output missing `results`.
5. `run_scenario.py ghost-invoice` → status says *completed*, Ghostwatch flags **ghost completion (critical)**: "your agent says it's working".
6. Fix the parser (one-line change) → click Replay (sandbox) → worker replays with recorded tool outputs → comparison shows `fixed`, step diff highlights `parse_results` failed → completed.
7. Show that live replay requires explicit authorization.
