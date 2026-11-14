# Backend progress — updated 2026-11-14T13:05Z

## Status: B1–B3 done and green in CI; B4 code written but uncommitted and untested; session stopped early (usage limit). Docker still not installed locally.

## Live endpoints (implemented + tested against contract, in CI against Postgres)
- GET /health
- POST /agents, GET /agents, GET /agents/{agent_id}

## In progress
- [B4] Executions (#6). Written, NOT committed, NOT tested: `app/services/executions.py` (create, list with all filters and sort, detail), `app/api/v1/executions.py`, router registered in `app/api/v1/__init__.py`. The list query compiles to the expected SQL offline. Still to do: `tests/test_executions.py`, a `make_replay` factory, CI run, commit.
- Also uncommitted: `app/services/agents.py` now uses `postgresql.distinct_on` (SQLAlchemy 2.1 deprecates `.distinct(expr)`), and `pyproject.toml` sets pytest `filterwarnings = ["error"]`. Neither has run against Postgres yet.

## Next up (dependency order; issue numbers in brackets)
- B4 (#6) → B5 (#7) → B6 (#8) → B7 (#9) → B15 (#10) → SYNC 1 (#32)
- Then B10 (#11) → B8 (#12) → B11 (#13) → B9 (#14) → B16 (#15); P1: B12 (#16), B13 (#17), B14 (#18)

## How verification works right now
- Docker is not installed on Jayden's machine, so database tests are skipped locally and run only in the CI `backend` job (Postgres service). Every commit so far was pushed and its CI run checked: B1 13 tests, B2 37, B3 73, all passing.
- Not yet done for B3: a real HTTP smoke test against a local database (needs Docker).

## Decisions (ambiguities resolved; "→ Adit" marks ones the frontend should know about)
- **Contract v1.1** (on main): agent-level anomalies carry the most recent related execution in `execution_id`; null only if none exists → Adit.
- **CODEOWNERS** (on main) lists both developers on every path, so the other person's review satisfies the Code Owner rule.
- **`AgentStats.success_rate` is all-time; `health` uses the last 20 terminal executions** → Adit. `avg_duration_ms` is a rounded integer.
- **`POST /agents` update semantics:** fields left out of the body keep their stored value; an explicit `null` clears.
- **`GET /agents`** accepts `sort` = `name` (default) or `created_at`, with `-` for descending; `health` accepts a comma list.
- **Unknown or malformed ids in a path return `404 not_found`**, never 422 → Adit.
- **Validation `details`**: `loc` is an array of strings/numbers, e.g. `["body", "slug"]` → Adit.
- **405 responses** use the envelope with code `bad_request` (the contract lists no code for 405).
- **`/health`** → Adit. `llm_configured` is true when the configured provider can run (`rule_based`: always; `fable`: key set). `llm_model` is null for `rule_based`.
- **Planned, not built yet:** timed-out executions get a templated `TimeoutError`; the sweeper appends an `execution.timed_out` event; duplicates are filtered before the terminal check; a terminal event leaves running steps running; `POST /executions` with an unknown agent → 404; request timestamps must be timezone-aware strings; `started_after` inclusive, `started_before` exclusive; stats `bucket` defaults to `hour` for `24h`, `day` otherwise; `cost_usd` stays null until B14; `PATCH /anomalies/{id}` comes with the P1 batch.
- **Test client** uses `httpx2` (Starlette 1.10 deprecates `httpx` for its TestClient).

## Contract change requests (open)
- none

## Known issues / tech debt
- F1–F13 (#19–#31) are unassigned until Adit accepts the collaborator invite.
- `adit/frontend` was fast-forwarded to main (contract v1.1 + CODEOWNERS) before Adit had pushed anything.

## How to run
- `cp .env.example .env` (done locally), `docker compose up -d`, then `cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload`
- Tests: `cd backend && uv run ruff check . && uv run pytest -q` (database tests skip locally without Postgres)
