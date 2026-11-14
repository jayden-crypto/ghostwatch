# Backend progress — updated 2026-11-14T20:50Z

## Status: every backend P0 issue is done (B1–B11, B15, B16). 417 backend tests and 22 SDK tests pass locally on docker compose Postgres. P1 (B12–B14) not started. Nothing from the frontend side exists in the repo yet.

## Live endpoints (implemented, tested against the contract, documented in docs/API.md)
- GET /health
- POST /agents 🔑, GET /agents, GET /agents/{agent_id}
- POST /executions 🔑, GET /executions, GET /executions/{execution_id}
- POST /executions/{execution_id}/events 🔑, GET /executions/{execution_id}/trace, GET /executions/{execution_id}/events
- GET /stats/overview, GET /stats/timeseries
- GET /anomalies, GET /anomalies/{anomaly_id}
- POST /investigations/{execution_id}, GET /investigations/{execution_id}, GET /investigations

Not implemented (404 envelope): PATCH /anomalies/{anomaly_id}, POST /executions/{execution_id}/replay, GET /replays, GET /replays/{replay_id}, POST /replays/{replay_id}/claim. `cost_usd` is always null until B14.

## In progress
- nothing

## Next up
- P1, in order: B12 replay API (#16) → B13 SDK sandbox replay + worker (#17) → B14 token cost (#18), plus PATCH /anomalies/{anomaly_id}
- Review Adit's X1 fixtures PR (#2) when it appears. `backend/tests/fixture_map.py` guesses his file names from the brief and will probably need adjusting; the conformance test fails loudly on any unmapped or invalid fixture.
- Open the `jayden/backend` → `main` PR when Jayden says so (he asked for it not to be opened yet).

## Not verified
- The Fable provider has never called the real API: it is tested with a fake client only. Needs `ANTHROPIC_API_KEY` and `LLM_PROVIDER=fable` in `.env`.
- No fixtures exist, so the fixture half of B15 has never run (it skips with a stated reason).
- Nothing has been exercised from a browser: there is no frontend in the repo.

## How to run
- `docker compose up -d`, then `cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app`
- Live API docs: http://localhost:8000/docs. Reference with real examples: `docs/API.md`
- Seed: `cd demo && uv run python seed.py` (baselines plus the support-triage incidents; `--all` adds the schema-change and ghost-invoice failures; `--append` if data already exists)
- One demo step: `cd demo && uv run python run_scenario.py list`
- Tests: `cd backend && uv run ruff check . && uv run pytest -q`; `cd sdk/python && uv run pytest -q`
- Smoke test over real HTTP against a running server: `cd backend && uv run python -m scripts.smoke`
- Regenerate docs/API.md from a seeded server: `cd backend && uv run python -m scripts.api_docs`
- On Jayden's machine `docker` is at `~/.docker/bin` and is not on PATH in non-login shells.
- The local dev database holds smoke-test and demo runs left over from verification. Reset it with `docker compose down -v` (Jayden's call) before seeding for the demo.

## What the frontend should know → Adit
- **Ids in paths**: an unknown or malformed id is always `404 not_found`, never 422.
- **Validation errors**: `details` is `[{loc, msg}]`; `loc` is an array such as `["body", "slug"]`.
- **Agents**: `success_rate` is all-time; `health` uses the last 20 terminal executions and open anomalies, so a high success rate can sit next to `failing`. `avg_duration_ms` is a rounded integer.
- **Executions list**: `started_after` inclusive, `started_before` exclusive. Unknown duration, tokens and cost sort last in both directions.
- **Timed-out executions**: `error` is `{type: "TimeoutError", message: "Execution timed out after <n> ms.", stacktrace: null}`.
- **Truncation**: `input`, `output`, `metadata` over 64 KB become the contract marker. Error messages, stack traces and log messages stay strings, cut to 64 KB with a `[truncated: N bytes in total]` note.
- **Trace**: `depth` 0 for a step whose parent is unknown; `offset_ms` never negative. A completed run with zero steps returns `steps: []` and a critical `ghost_completion` anomaly.
- **Stats**: a window is whole UTC buckets ending with the current one (24 hours, 7 days, 30 days). Overview totals equal the sum of the default timeseries. Running executions are in the overview, not in the points. `open_anomalies` and `total_agents` are not windowed.
- **Anomalies**: agent-level ones carry an `execution_id` (contract v1.1). `PATCH` is not implemented.
- **Investigations**: start automatically on failed or timed_out executions and on anomalies of high or above. `confirmed` only comes from a signature; with `rule_based` and no matching signature the root cause is `insufficient_evidence`. `provider` is `fable` only when the model's answer was used; otherwise `rule_based`, with the reason in `evidence_gaps`. `summary` is a deterministic template. POST returns the in-flight investigation (202) if one is queued or running.
- **`/health`**: `llm_configured` is true when the configured provider can run; `llm_model` is null for `rule_based`.
- **Demo data**: the fake LLM is `demo-llm-1`, which has no price, so `cost_usd` is null on every demo run.

## Decisions (backend-internal)
- 405 responses use the envelope with code `bad_request` (the contract lists no code for 405).
- `POST /agents` keeps stored values for fields left out of an update; explicit `null` clears.
- Ingestion: duplicates are dropped before every other rule; a step id can be started once; a terminal event leaves running steps running; payloads are stored with defaults filled in; durations come from client timestamps, clamped at 0. The execution row is locked for the batch.
- The sweeper times an execution out by appending an `execution.timed_out` event through the ingest path, re-checking staleness under the row lock. It also runs any investigation still queued.
- Baseline: last 20 completed, non-replay executions that started no later than the one evaluated. p95 is nearest-rank. Agent-level rules fire only on an execution that is itself part of the pattern.
- `tool_http_error` only considers the last tool call up to the failing step, so a 429 the agent recovered from is not blamed for a later failure.
- Fable requests use structured outputs (`output_config.format`), effort `medium`, and the server-side refusal fallback; `model` records the model that answered. Forced tool use is not used: the model rejects it.
- SDK: zero runtime dependencies; the execution is created lazily by the background thread, so the agent never waits on Ghostwatch. `@gw.llm_call` reads token usage from a returned `usage` dict.
- Demo seed backdates over 6 days so all of it is inside the 7-day window. Scenarios change only a fake service.
- The schemas enforce contract invariants (citations resolve, `signature` exactly when `confirmed`, `report` exactly when `completed`, a live replay is authorized, ≥ 1 evidence item, title ≤ 80 chars), so fixtures that break them fail B15.
- OpenAPI: FastAPI's default validation-error schema is removed; every documented error is the envelope.
- Tooling: tests use `httpx2`; pytest treats warnings as errors; long literal lines are allowed in tests.

## Contract change requests (open)
- none

## Known issues / tech debt
- Issues #3–#15 stay open until `jayden/backend` merges to `main`.
- `GHOSTWATCH_API_KEY` in `.env` is still the placeholder from `.env.example`.
