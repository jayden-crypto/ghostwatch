# Backend progress — updated 2026-11-14T17:10Z

## Status: all backend P0 code is written: B1–B11 and B15, plus B9 (investigations). 409 backend tests pass locally on docker compose Postgres; SDK 22; demo lint clean. B16 (docs) and P1 (B12–B14) not started. CI for the B9 commit was not checked before the session ended.

## Live endpoints (implemented + tested against the contract)
- GET /health
- POST /agents 🔑, GET /agents, GET /agents/{agent_id}
- POST /executions 🔑, GET /executions, GET /executions/{execution_id}
- POST /executions/{execution_id}/events 🔑, GET /executions/{execution_id}/trace, GET /executions/{execution_id}/events
- GET /stats/overview, GET /stats/timeseries
- GET /anomalies, GET /anomalies/{anomaly_id}
- POST /investigations/{execution_id}, GET /investigations/{execution_id}, GET /investigations

Not implemented (404 envelope): PATCH /anomalies/{id}, /replays*, POST /executions/{id}/replay.

## In progress
- nothing mid-edit. First thing next session: check the CI run of the latest commit on jayden/backend.

## Next up
- B16 docs/API.md + OpenAPI descriptions (#15), then SYNC 2 (#33)
- P1: B12 replay API (#16), B13 SDK sandbox replay + worker (#17), B14 cost (#18), PATCH /anomalies/{id}
- Not yet done for B9: a live call to the real Fable API (needs ANTHROPIC_API_KEY in .env and LLM_PROVIDER=fable). The provider is tested only with a fake client.

## How to run
- `docker compose up -d`, then `cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app`
- Seed: `cd demo && uv run python seed.py` (add `--all` for the two failures; `--append` if data exists)
- Scenarios: `cd demo && uv run python run_scenario.py list`
- Smoke test against a running server: `cd backend && uv run python -m scripts.smoke`
- Tests: `cd backend && uv run pytest -q`; `cd sdk/python && uv run pytest -q`
- `docker` lives at ~/.docker/bin and is not on PATH in non-login shells on Jayden's machine.

## Investigations (B9) in brief → Adit
- Auto-queued in the ingest transaction on failed/timed_out (auto_failure) or an anomaly of high or above (auto_anomaly); runs as a background task. The sweeper also runs any still-queued ones.
- `confirmed` only from a signature: missing_key_in_upstream_output, retry_exhaustion, tool_http_error, timeout_in_step, ghost_completion. With rule_based and no matching signature the root cause is `insufficient_evidence`; an LLM hypothesis is at most `probable`.
- `summary` is a deterministic template. `provider` is `fable` only when the model's answer was used; on any LLM failure it is `rule_based` and `evidence_gaps` says why.
- POST returns 202 with the in-flight investigation if one is queued or running, 200 with the completed one unless `force`, 409 while the execution is running.
- Fable requests use structured outputs and opt into the server-side refusal fallback; `model` is the model that actually answered.
- The local dev database holds smoke-test and demo runs from verification; reset with `docker compose down -v` before seeding for the demo.

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
