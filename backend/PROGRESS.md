# Backend progress — updated 2026-11-21T20:19Z

## Status: every backend issue is done: P0 (B1–B11, B15, B16) and P1 (B12 replay API, B13 SDK sandbox replay and worker, B14 cost, PATCH /anomalies/{anomaly_id}). Every contract endpoint is implemented. 617 backend tests (none skipped: the 145 contract fixtures now validate too) and 39 SDK tests pass locally on docker compose Postgres. PR #36 (`jayden/backend` → `main`) was approved by Adit at 2b3e4ec and squash-merged as 80151dc on 2026-11-16, so the whole backend, the SDK and the demo are on `main`. Adit confirmed contract v1.1 and v1.2 as they are on `main` (2026-11-18).

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
- `docs/DEMO_SCRIPT.md` (shared, X4 #34) reached `main` with PR #40 (4ac9ad6, approved by Adit). On 2026-11-21 the whole script ran again on a production build of `main` (4ac9ad6) against a scratch backend: the terminal output of steps 2, 3, 5 and 7 and every screen checked matched; the trace, investigation and replay pages were often slow to start their API request (1–7 s) even with the pane displayed, while list pages took under 300 ms (details in the script's log). Adit suggested moving setup step 4 to a production build; not decided (the script's log lists what that change would also need). #34 stays open until three human rehearsals and the backup recording. Its terminal half was rehearsed twice from an empty database on 2026-11-16 and quotes real output. On 2026-11-17 the whole script ran once with the frontend from `main` in live mode against a scratch backend (macOS, Node 26): every step matched after two corrections to the script, so the "not verified live" marks are gone. Whether a Claude session's run counts towards the three full runs is for Jayden and Adit to decide. Pages were sometimes slow to render. On 2026-11-18 one stall was reproduced: a trace page waits for an animation frame to show its streamed content, a browser pane that is not on screen draws none, and the API request does not start until it is shown. This happens on the dev server and on a production build, and still after PR #39. The 2026-11-17 case where the request had already answered is unexplained (see the script's setup step 5). The same run found that demo runs do report tokens (about 199 for a healthy research-assistant run); only cost is null. Found while rehearsing: a single failed run raises no anomaly (only the automatic investigation), so the plan's "anomaly + auto investigation appear" for the schema-change step is not what happens; the script says so.
- Nothing else queued on the backend side. The Windows encoding fix (PR #37) was approved by Adit at 83e49cb and squash-merged as 8377e7f on 2026-11-16: every file read and write in `backend/` and `demo/` names UTF-8. Adit reran it on Windows 11 with cp1252 as the default: the three tests that failed now pass (389 passed, 209 skipped for lack of Postgres there). To keep it that way, `PYTHONWARNDEFAULTENCODING=1 uv run pytest -q` turns any read without an encoding into an error.
- Optional, raised by Adit and not done: a `.env` saved by Windows Notepad or PowerShell 5.1 can start with a UTF-8 byte-order mark, which `utf-8` keeps as part of the first key; `utf-8-sig` in `demo/settings.py` and `env_file_encoding` would tolerate it. Nobody has hit it.

## Not verified
- The Fable provider has never called the real API: it is tested with a fake client only. Needs `ANTHROPIC_API_KEY` and `LLM_PROVIDER=fable` in `.env`.
- One fixture investigation (`contract/fixtures/`, from Adit's PR #35, merged to `main` as 36e3390) has provider `fable` to exercise that UI state; it is example data, not a real model run.
- A live replay (`mode: "live"`) has been tested in the SDK against a stub only, never against the real API.
- The frontend reached `main` with PR #38 (squash b36be58). Against this backend it has been run only along the demo path (`docs/DEMO_SCRIPT.md`, 2026-11-17, Chromium in the Claude desktop app's browser pane, dev server): Overview, Agents, Anomalies, the trace page with its Investigation tab, the Replay dialog in both modes and the replay comparison. No console errors and no unexpected API errors. On 2026-11-18 a production build of `main` (fe86776) was checked against a scratch backend on port 8001: the five list pages, some filters across a reload, Acknowledge, Resolve and Reopen (API side), Overview, agent detail and the other trace tabs. On 2026-11-21 demo steps 1–7 ran in order on a production build of 4ac9ad6. What was and was not covered is listed under the script's rehearsal log. Closing F12 (#28) is Adit's call.

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
- Session handoffs are committed, one file per side (#41): this side writes only `.claude/state/handoff-backend.md`, so the two sessions never conflict. The hook-written `snapshot.md` stays git-ignored. Durable status still lives in the PROGRESS files.
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
