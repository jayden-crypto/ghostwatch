# Frontend progress — updated 2026-11-14T18:25Z

## Status: first session done — repo inspected, source-of-truth files read, execution plan posted to Adit. No app code yet; waiting for Adit's "go".

## Pages (mock ✓ / live ✓)
- Overview `/`: mock ✗ live ✗
- Agents `/agents`, `/agents/[id]`: mock ✗ live ✗
- Executions `/executions`: mock ✗ live ✗
- Trace explorer `/executions/[id]`: mock ✗ live ✗
- Traces `/traces`: mock ✗ live ✗
- Anomalies `/anomalies`: mock ✗ live ✗
- Investigations `/investigations`, `/investigations/[executionId]`: mock ✗ live ✗
- Replays `/replays`, `/replays/[id]` (P1): mock ✗ live ✗
- Settings `/settings` (P1): mock ✗ live ✗

## In progress
- nothing. Nothing is mid-edit.

## Next up (order after "go")
1. F1a (#19): `create-next-app` scaffold only (TS strict, Tailwind, App Router) in `frontend/`.
2. `lib/api/types.ts` (first slice of F2 #20) mirroring contract v1.1 — X1 needs it.
3. X1 (#2): `contract/fixtures/` + `frontend/scripts/validate-fixtures.ts`; PR from branch `contract/fixtures` to `main`. Jayden is blocked on this for B15.
4. F1b (#19): tokens, fonts, shell, nav, MOCK DATA badge — while Jayden reviews X1.
5. F2 (#20) → F3 (#21) → F6 (#22) → F4 (#23) → F5 (#24) → early live pass (F12 #28) → F7 (#25) → F8 (#26) → F9 (#27) → F13 (#29) → F10 (#30) → F11 (#31).

Issue numbers follow the table order in PROJECT_PLAN §7, not F-number order: F6 is #22, F4 #23, F5 #24, F7 #25, F8 #26, F9 #27, F12 #28, F13 #29, F10 #30, F11 #31.

## Waiting on backend (endpoint → why)
Per `backend/PROGRESS.md` on `origin/jayden/backend` at e9f4c53 (read 2026-11-14T18:20Z), these are already implemented, so nothing below blocks a live switch once the backend runs on this machine:
/health, /agents*, /executions*, /executions/{id}/trace, /executions/{id}/events, /stats/*, /anomalies (GET), /investigations*.
- POST /executions/{id}/replay, /replays* (B12, B13) → replay dialog + comparison stay on mocks (F10)
- PATCH /anomalies/{id} (P1) → acknowledge/resolve buttons stay "Not implemented"
- cost_usd (B14) → null until then; UI shows "—"
- `jayden/backend` → `main` merge → needed before I can fill the frontend job in `.github/workflows/ci.yml` (the file exists only on his branch)

## Environment (this machine: Windows 11)
- node v24.19.0 OK · npm 11.17.0 OK · git 2.55.0 OK · uv 0.12.16 OK · python 3.12.14 OK
- gh: MISSING (needs install + `gh auth login` by Adit) → blocks opening PRs from the CLI (X1)
- docker: MISSING → blocks running Jayden's backend + Postgres locally for the live switch
- Playwright browsers: not installed → `npx playwright install chromium` needed before F13 smoke test (download, no admin)
- git identity was unset; set repo-locally to the GitHub noreply address for `adituppal7`

## Decisions
- **Mode is global, never mixed.** `NEXT_PUBLIC_API_MODE` switches every request at once. Mixing fixture replays with live executions would show ids that do not resolve and fixture data without a badge that applies to the whole screen. In live mode an unbuilt endpoint shows its real 404 envelope as "Not available on this backend yet".
- **Fixture file names use only the (resource, operation) pairs in Jayden's `backend/tests/fixture_map.py`**; anything else fails B15 on purpose. Raw events are `executions.events.<variant>.json`.
- **Fixtures obey the invariants his schemas enforce beyond the contract text**: `signature` set exactly when `confirmed`; `report` set exactly when `completed`; live replay always authorized; ≥ 1 evidence item on anomalies and facts; anomaly title ≤ 80 chars; fact/hypothesis/recommendation ids `F1`/`H1`/`R1` style.
- **Fixture step names, types and configs copy the real demo agents** (`demo/agents/*.py`), so mock and live look the same. The demo agents are flat (depth 0); nested-depth and 250-step traces are generated in `frontend/tests/`, not in `contract/fixtures/`.
- **`validate-fixtures.ts`** generates a TS file with each fixture inlined as a literal `satisfies <Type>` and runs `tsc --noEmit` (JSON imports widen enums to `string`, so a plain import cannot check them), then checks id/timestamp format, cross-file id resolution and enum coverage at runtime. I will also run the fixture layer of Jayden's `test_conformance.py` from a read-only worktree before opening the PR.
- **GET /investigations/{execution_id} 404** is the "no investigation yet" state, not an error.
- **The raw-event item type** (unnamed in contract §6) is called `StoredEvent` in `types.ts`, matching the backend.
- **Settings shows the data mode read-only**; it is a build-time env var.
- **Running-step bars** end at the browser's "now"; labelled as live, and clamped to the execution start.
- **`/` trend chart** has no `running` series (the API leaves running executions out of timeseries points); the running count is a stat tile.
- **Schedule is counted from Adit's "go" (G+0)**, because T+0 is not recorded in the repo.

## Contract change requests (open)
- none

## Known issues
- Kickoff said anomalies and investigations are not built; Jayden's branch says they are (B8, B9 committed). To confirm with Jayden at the first live pass.
- `frontend/` and `contract/fixtures/` did not exist before this file; `.github/workflows/ci.yml` and `docker-compose.yml` exist only on `jayden/backend`.
- Issues #2 and #19–#31 have no assignee yet.

## How to run
- Not runnable yet (no scaffold). Target: `cd frontend && npm i && npm run sync-fixtures && npm run dev`
