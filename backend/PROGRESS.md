# Backend progress — updated 2026-11-14T12:24Z

## Status: X0 bootstrap done; backend execution plan written; no backend code yet. Waiting for Jayden's "go" to start B1.

## Live endpoints (implemented + tested against contract)
- none

## In progress
- nothing (first session ended at the plan; B1 starts on "go")

## Next up (dependency order; issue numbers in brackets)
- P0: B1 (#3) → B2 (#4) → B3 (#5) → B4 (#6) → B5 (#7) → B6 (#8) → B7 (#9) → B15 (#10) → SYNC 1 (#32)
- P0 after SYNC 1: B10 (#11) → B8 (#12) → B11 (#13) → B9 (#14) → B16 (#15) → SYNC 2 (#33)
- P1 from T+30: B12 (#16) → B13 (#17) → B14 (#18)

## Blockers
- Docker is not installed on Jayden's machine (`docker: command not found`). Tests need real Postgres, so B1's database checks and everything from B2 on cannot be verified until Docker Desktop or OrbStack is installed and running.

## Decisions (ambiguities resolved; "→ Adit" marks ones the frontend should know about)
Planned resolutions, recorded before implementation. Each is confirmed or revised when its issue lands.
- **Agent-level anomalies carry an execution id** → Adit. Contract §8 says both "`execution_id` null for agent-level anomalies such as repeated_timeouts" (type comment) and "`execution_id` = most recent one" (rule table). Following the rule table: `repeated_timeouts` and the agent-level branch of `repeated_tool_failure` set `execution_id` to the execution that triggered them. The field stays nullable in the schema, so either reading validates.
- **`AgentStats.success_rate` is all-time; `health` uses the last 20 terminal executions** → Adit. An agent can therefore show a high all-time success rate and still be `failing`.
- **`/health`** → Adit. `llm_provider` is the configured `LLM_PROVIDER`. `llm_configured` is true when that provider can run (`rule_based`: always; `fable`: `ANTHROPIC_API_KEY` is set). `llm_model` is `LLM_MODEL` for `fable`, `null` for `rule_based`.
- **Timed-out executions get a synthesised `error`** → Adit. `execution.timed_out` has an empty payload, so `error` is the template `{type: "TimeoutError", message: "No event received for <n> ms (timeout_ms=<n>).", stacktrace: null}`.
- **The sweeper writes an event.** To keep "events are the only way state changes" true, the stale sweeper appends an `execution.timed_out` event (next `seq`) through the normal ingest path rather than updating the row directly.
- **Duplicates are filtered before the terminal check.** A retried batch whose events were all already stored returns `202` with `duplicates: N` even if the execution is terminal; `409 execution_already_terminal` applies only to new non-`log` events.
- **A terminal event does not close running steps.** Steps still `running` when `execution.completed` arrives stay `running`; that is `ghost_completion` evidence.
- **`POST /executions` with an unknown `agent_id`** returns `404 not_found`. Request `config` may be partial; responses always include `model`, `params`, `expected_steps`, `timeout_ms`.
- **Timestamps in requests** must be timezone-aware (converted to UTC); naive values get `422`. Durations come from client event timestamps, floored to whole ms and clamped at 0.
- **Stats.** `bucket` defaults to `hour` for `24h` and `day` for `7d`/`30d`. Timeseries returns N buckets ending with the current partial bucket (24 / 7 / 30), aligned to UTC boundaries. Overview uses a rolling `started_at >= now − window`.
- **`cost_usd` stays `null` until B14 (P1).** That is contract-legal ("null = unknown") and avoids any guessed price.
- **B5 terminal path is built with seams.** `finalize_execution` calls the anomaly engine, investigation queue and pricing through functions that B8, B9 and B14 fill in. Until then they do nothing; they never return placeholder results.
- **`PATCH /anomalies/{id}`** is P1 in the contract and has no issue of its own; it will be built in the P1 window alongside B12.
- **`POST /investigations/{id}` on a still-running execution** returns `409 conflict`.
- **Git identity** for this clone is set locally to the GitHub noreply address, because no global git identity was configured.

## Contract change requests (open)
- none. The `execution_id` wording conflict in §8 (first decision above) does not need a contract change, but should be tidied in the next contract PR.

## Known issues / tech debt
- CODEOWNERS lists a single owner for `/backend/` and `/frontend/`. With "require review from Code Owners" on, a PR whose only code owner is its author cannot get a code-owner approval, so Adit's frontend PRs to `main` would need Jayden (admin) to merge them. To be confirmed on the first PR; fix is a shared CODEOWNERS PR. Raised with Jayden.
- F1–F13 (#19–#31) are unassigned until Adit accepts the collaborator invite.

## How to run
- Not runnable yet. Target after B1/B2: `docker compose up -d && cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload`
