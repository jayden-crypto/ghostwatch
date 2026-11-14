# Backend progress — updated 2026-11-14T14:14Z

## Status: B1–B7 and B15 done and green in CI (249 tests). Backend is ready for SYNC 1, about T+2 into the schedule. Not yet run locally against Postgres: Docker is still not installed on Jayden's machine.

## Live endpoints (implemented + tested against the contract, in CI against Postgres 16)
- GET /health
- POST /agents 🔑, GET /agents, GET /agents/{agent_id}
- POST /executions 🔑, GET /executions (all filters, sort, pagination), GET /executions/{execution_id}
- POST /executions/{execution_id}/events 🔑
- GET /executions/{execution_id}/trace, GET /executions/{execution_id}/events
- GET /stats/overview, GET /stats/timeseries

Not implemented yet (unrouted, so they return the 404 envelope): /anomalies*, /investigations*, /replays*, POST /executions/{id}/replay.

## In progress
- nothing

## Next up (dependency order; issue numbers in brackets)
- B10 SDK core (#11) → B8 anomaly engine (#12) → B11 demo (#13) → B9 investigations (#14) → B16 docs (#15) → SYNC 2 (#33)
- P1 from T+30: B12 (#16) → B13 (#17) → B14 (#18), plus `PATCH /anomalies/{id}`
- B5's terminal path still has to call the anomaly engine (B8), queue the auto-investigation (B9) and price the run (B14). Until then: no anomalies are raised, no investigation is queued, `cost_usd` is null.

## Open before SYNC 1 can actually happen
- **Docker** on Jayden's machine. Without it nobody can run the backend locally for Adit to point at, and I have not done a real-HTTP smoke test of B3–B7 (only the in-process test client in CI).
- **X1 fixtures (#2)**: nothing pushed yet; Adit has not accepted the collaborator invite. The fixture conformance test skips until `contract/fixtures/` has files, then fails on any fixture that does not validate or is not mapped in `backend/tests/fixture_map.py`.

## How verification works right now
- Database tests are skipped locally (no Postgres) and run in the CI `backend` job. Each commit was pushed and its CI run checked: B1 13 tests, B2 37, B3 73, B4 103, B5 136, B6 153, B7 168, B15 249 passed (2 skipped: fixture tests).
- `filterwarnings = error`: a deprecation in our code fails the suite.

## Decisions (ambiguities resolved; "→ Adit" marks ones the frontend should know about)
- **Contract v1.1** (on main): agent-level anomalies carry the most recent related execution in `execution_id`; null only if none exists → Adit.
- **CODEOWNERS** (on main) lists both developers on every path.
- **Unknown or malformed ids in a path return `404 not_found`**, never 422 → Adit.
- **Validation `details`**: `loc` is an array of strings/numbers, e.g. `["body", "slug"]` or `["body", "events", 2, "payload", "step_id"]` → Adit.
- **405** uses the envelope with code `bad_request` (the contract lists no code for 405).
- **`/health`** → Adit: `llm_configured` is true when the configured provider can run (`rule_based` always; `fable` only with a key); `llm_model` is null for `rule_based`.
- **Agents** → Adit: `success_rate` is all-time, `health` uses the last 20 terminal executions; `avg_duration_ms` is a rounded integer. `POST /agents` keeps stored values for fields left out; explicit `null` clears. `GET /agents` sorts by `name` (default) or `created_at`; `health` accepts a comma list.
- **Executions** → Adit: `started_after` is inclusive, `started_before` exclusive. Unknown tokens/cost/duration sort last in both directions. `q` matches an execution id prefix or a case-insensitive part of the agent name. `POST /executions` with an unknown `agent_id` or `replay_of` → 404. Request timestamps must be timezone-aware strings (epoch numbers and naive times → 422).
- **Ingestion**: duplicates are dropped before every other rule, so retrying the final batch of a finished execution returns 202 with `duplicates`. A step id may be started once, ever; ending an unknown, foreign or already-ended step → 422. A terminal event leaves running steps running (ghost-completion evidence). Event payloads are stored with defaults filled in. Durations come from client timestamps and are clamped at 0.
- **Truncation**: `input`, `output` and `metadata` over 64 KB become the contract marker (in the event and the step). `error.message`, `error.stacktrace` and log messages keep their string type and are cut to 64 KB with a `[truncated: N bytes in total]` note (stack traces keep the tail) → Adit.
- **Timed-out executions** → Adit: `error` is `{type: "TimeoutError", message: "Execution timed out after <n> ms.", stacktrace: null}`.
- **Trace**: a step whose parent is unknown, or whose parent chain loops, is laid out as a root (`depth` 0); `parent_step_id` is returned as sent. `offset_ms` is clamped at 0 → Adit.
- **Stats** → Adit: a window is whole UTC buckets ending with the current one (24h = 24 hours, 7d = 7 days, 30d = 30 days; `30d&bucket=hour` = 720 points). Overview totals equal the sum of the default timeseries. `bucket` defaults to `hour` for `24h`, `day` otherwise. `open_anomalies` and `total_agents` are current totals, not windowed. Running executions are in the overview but not in timeseries points.
- **Schemas enforce contract invariants**: report citations resolve; `signature` set exactly when `confirmed`; `report` set exactly when `completed`; a live replay is always authorized; anomalies and facts have ≥ 1 evidence item; anomaly `title` ≤ 80 chars. Fixtures that break these fail B15.
- **Planned, not built yet**: sweeper appends an `execution.timed_out` event through the ingest path; `PATCH /anomalies/{id}` with the P1 batch; `cost_usd` null until B14; investigating a running execution → 409.
- **Tooling**: tests use `httpx2` (Starlette 1.10 deprecates `httpx` for its TestClient). Git identity for this clone is the GitHub noreply address.

## Contract change requests (open)
- none

## Known issues / tech debt
- No real-HTTP smoke test of B3–B7 yet (needs Docker).
- `docker-compose.yml` itself is untested for the same reason.
- F1–F13 (#19–#31) are unassigned until Adit accepts the collaborator invite.
- Issues #3–#10 are still open; they close when `jayden/backend` merges to `main`.

## How to run
- `cp .env.example .env` (done on Jayden's machine), `docker compose up -d`, then `cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload`
- Tests: `cd backend && uv run ruff check . && uv run pytest -q` (database tests skip locally without Postgres; CI runs them)
- API docs once running: http://localhost:8000/docs
