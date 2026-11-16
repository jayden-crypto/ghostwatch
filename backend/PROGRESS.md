# Backend progress — updated 2026-11-16T15:35Z

## Status: every backend issue is done: P0 (B1–B11, B15, B16) and P1 (B12 replay API, B13 SDK sandbox replay and worker, B14 cost, PATCH /anomalies/{anomaly_id}). Every contract endpoint is implemented. 617 backend tests (none skipped: the 145 contract fixtures now validate too) and 39 SDK tests pass locally on docker compose Postgres. PR #36 (`jayden/backend` → `main`) was approved by Adit at 2b3e4ec and squash-merged as 80151dc on 2026-11-16, so the whole backend, the SDK and the demo are on `main`. Adit's review raised no objection to contract v1.1 and v1.2.

## Live endpoints (implemented, tested against the contract, documented in docs/API.md)
- GET /health
- POST /agents 🔑, GET /agents, GET /agents/{agent_id}
- POST /executions 🔑, GET /executions, GET /executions/{execution_id}
- POST /executions/{execution_id}/events 🔑, GET /executions/{execution_id}/trace, GET /executions/{execution_id}/events
- GET /stats/overview, GET /stats/timeseries
- GET /anomalies, GET /anomalies/{anomaly_id}, PATCH /anomalies/{anomaly_id}
- POST /investigations/{execution_id}, GET /investigations/{execution_id}, GET /investigations
- POST /executions/{execution_id}/replay, GET /replays, GET /replays/{replay_id}, POST /replays/{replay_id}/claim 🔑

Not implemented: nothing.

## In progress
- nothing

## Next up
- Reported by Adit in his review of PR #36, not fixed yet: three tests in `backend/tests/test_openapi.py` fail on Windows because files are read with `read_text()` and no encoding (cp1252 misreads the 🔑 marker in the contract). The same call is in `backend/tests/test_openapi.py` lines 13 and 121, `backend/tests/test_demo_e2e.py` line 332 and `demo/settings.py` line 14. The fix is `read_text(encoding="utf-8")`. CI runs on Linux and is green.

## Not verified
- The Fable provider has never called the real API: it is tested with a fake client only. Needs `ANTHROPIC_API_KEY` and `LLM_PROVIDER=fable` in `.env`.
- One fixture investigation (`contract/fixtures/`, from Adit's PR #35, merged to `main` as 36e3390) has provider `fable` to exercise that UI state; it is example data, not a real model run.
- A live replay (`mode: "live"`) has been tested in the SDK against a stub only, never against the real API.
- Nothing has been exercised from a browser: there is no frontend in the repo.

## How to run
- `docker compose up -d`, then `cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app`
- Live API docs: http://localhost:8000/docs. Reference with real examples: `docs/API.md`
- Seed: `cd demo && uv run python seed.py` (baselines plus the support-triage incidents; `--all` adds the schema-change and ghost-invoice failures; `--append` if data already exists)
- One demo step: `cd demo && uv run python run_scenario.py list`
- Replay: `cd demo && uv run python replay.py worker --fixed` in one terminal (without `--fixed` the agents run as shipped), then `uv run python replay.py request <execution_id>` in another, or the dashboard's Replay button
- Tests: `cd backend && uv run ruff check . && uv run pytest -q`; `cd sdk/python && uv run pytest -q`
- Smoke test over real HTTP against a running server: `cd backend && uv run python -m scripts.smoke`
- Regenerate docs/API.md from a seeded server with a replay worker running against it (`cd demo && uv run python replay.py worker --fixed`): `cd backend && uv run python -m scripts.api_docs`
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
- **Anomalies**: agent-level ones carry an `execution_id` (contract v1.1). `PATCH /anomalies/{id}` takes `{status}` only; any status may follow any other (a resolved anomaly can be reopened), and only `open` ones count towards `open_anomalies` and agent `health`.
- **Replay** (contract v1.2): `POST /executions/{id}/replay` returns `pending`; nothing runs until a replay worker is up, so a replay can stay `pending` indefinitely. Poll `GET /replays/{id}` until `completed`; `comparison` is null before that. A replay whose agent fails is still `completed` (the outcome says how it went). `live` without `authorize_side_effects: true` is `422 side_effect_authorization_required`, and the flag must be the JSON value `true`. Replaying a running execution is `409`.
- **Replay sources**: every step of a replay execution has `metadata.replay_source` (`recorded`, `executed` or `blocked`), mirrored in `StepDiff.replay_source` (null for a `removed` step). A blocked step fails with error type `SandboxRecordingMissing`. The Replay dialog's old line ("nothing external runs") is wrong; the corrected copy is in the message of commit 4b7568d.
- **Replay demo result**: replaying the schema-change failure gives `same_failure` with the agent as shipped and `fixed` with the parser fix (web_search `recorded`, summarize `added` and `executed`).
- **Investigations**: start automatically on failed or timed_out executions and on anomalies of high or above. `confirmed` only comes from a signature; with `rule_based` and no matching signature the root cause is `insufficient_evidence`. `provider` is `fable` only when the model's answer was used; otherwise `rule_based`, with the reason in `evidence_gaps`. `summary` is a deterministic template. POST returns the in-flight investigation (202) if one is queued or running.
- **`/health`**: `llm_configured` is true when the configured provider can run; `llm_model` is null for `rule_based`.
- **Cost**: `cost_usd` is set when an execution ends, from each step's own `model` and tokens at Anthropic's published list prices (`backend/app/services/pricing.py`). It is null when no step reported tokens, and also when any step that reported tokens has an unpriced or missing model or reported only input or only output; a partial sum is never shown. It covers reported input and output tokens only: no prompt-cache, batch or fast-mode pricing. Executions that ended before B14 keep null.
- **Demo data**: the fake LLM is `demo-llm-1`, which has no price, so `cost_usd` is null on every demo run. Label it as unknown, not as $0.

## Decisions (backend-internal)
- No paid API calls: `LLM_PROVIDER=rule_based` everywhere (config default, `.env.example`, the demo, tests, docs examples). Fable is an optional provider that needs `ANTHROPIC_API_KEY`; nothing may claim the demo used it.
- `.claude/state/` (the session handoff and snapshot) is git-ignored and local to each machine, so the two sessions never conflict on it. Durable state lives in the PROGRESS files.
- 405 responses use the envelope with code `bad_request` (the contract lists no code for 405).
- `POST /agents` keeps stored values for fields left out of an update; explicit `null` clears.
- Ingestion: duplicates are dropped before every other rule; a step id can be started once; a terminal event leaves running steps running; payloads are stored with defaults filled in; durations come from client timestamps, clamped at 0. The execution row is locked for the batch.
- The sweeper times an execution out by appending an `execution.timed_out` event through the ingest path, re-checking staleness under the row lock. It also runs any investigation still queued.
- Baseline: last 20 completed, non-replay executions that started no later than the one evaluated. p95 is nearest-rank. Agent-level rules fire only on an execution that is itself part of the pattern.
- `tool_http_error` only considers the last tool call up to the failing step, so a 429 the agent recovered from is not blamed for a later failure.
- Fable requests use structured outputs (`output_config.format`), effort `medium`, and the server-side refusal fallback; `model` records the model that answered. Forced tool use is not used: the model rejects it.
- SDK: zero runtime dependencies; the execution is created lazily by the background thread, so the agent never waits on Ghostwatch. `@gw.llm_call` reads token usage from a returned `usage` dict.
- Demo seed backdates over 6 days so all of it is inside the 7-day window. Scenarios change only a fake service.
- Replay: the server never runs agent code. A worker (`gw.ReplayWorker`) polls for pending replays of agents it has registered, claims one (a conditional UPDATE, so exactly one worker wins) and runs the agent's own function with the original input. The comparison is computed when the replay's execution ends.
- Sandbox: recordings are matched per tool or step name in call order. A recorded failure is raised again as the same exception class when the agent's module or the builtins have it. A recording that was truncated (over 64 KB) is blocked rather than served, and a truncated original input fails the replay with `ReplayNotPossible`. A served LLM recording reports no tokens for the replay.
- Pricing: exact model ids only (no prefix or fuzzy matching), so a Bedrock or Vertex id is unpriced. Claude Haiku 5.5 uses its higher price when a step's input is over 100,000 tokens. Retired and retiring models are not in the table. Prices were read from the published page on 2026-11-15; update the table and the date together.
- `@gw.tool` without `side_effects` means `side_effects=True`. The demo's read-only tools (`web_search`, `retrieve_kb`) declare `side_effects=False`.
- The sandbox only governs `@gw.tool` and `@gw.llm_call`. Code an agent runs outside those decorators runs in every mode.
- The schemas enforce contract invariants (citations resolve, `signature` exactly when `confirmed`, `report` exactly when `completed`, a live replay is authorized, ≥ 1 evidence item, title ≤ 80 chars), so fixtures that break them fail B15.
- OpenAPI: FastAPI's default validation-error schema is removed; every documented error is the envelope.
- Tooling: tests use `httpx2`; pytest treats warnings as errors; long literal lines are allowed in tests.

## Contract change requests (open)
- none

## Known issues / tech debt
- The contract has no way for a worker to report that it could not start a replay. The worker instead opens the replay's execution and fails it with `ReplayNotPossible`, so the reason is visible. A replay that no worker ever claims stays `pending`.
- Issues #3–#15 stay open until `jayden/backend` merges to `main`.
- `GHOSTWATCH_API_KEY` in `.env` is still the placeholder from `.env.example`.
