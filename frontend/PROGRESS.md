# Frontend progress — updated 2026-11-15T10:00Z

## Status: X1 PR is open and waiting for Jayden's review. F1, F2, F3, F6, F5 and F4 are built and verified in mock mode. Nothing has been run against the live backend yet (no Docker on this machine).

## Pages (mock ✓ / live ✓)
- Overview `/`: mock ✓ live ✗ (untested)
- Executions `/executions`: mock ✓ live ✗ (untested)
- Trace explorer `/executions/[id]`: mock ✓ live ✗ (untested)
- Traces `/traces`: mock ✓ live ✗ (untested)
- Agents `/agents`, `/agents/[id]`: placeholder ("Not implemented"); `/agents/[id]` has no route yet, so agent links 404
- Anomalies `/anomalies`: placeholder
- Investigations `/investigations`, `/investigations/[executionId]`: placeholder
- Replays `/replays`, `/replays/[id]` (P1): placeholder; `/replays/[id]` has no route yet
- Settings `/settings` (P1): placeholder
- `/dev/components`: every enum badge and shared state on one page (not in the nav)

## Done
- **X1 (#2)**: PR https://github.com/jayden-crypto/ghostwatch/pull/35 (`contract/fixtures` → `main`), review requested from Jayden. 144 fixtures; passes `npm run validate-fixtures` and Jayden's `tests/test_conformance.py -k fixture` (145 passed at e9f4c53).
- **F1 (#19)**: scaffold, tokens, Geist, shadcn/ui, shell, Ctrl/⌘K palette (pages only).
- **F2 (#20)**: `lib/api/{client,live,mock,hooks,errors}.ts`, `npm run sync-fixtures`.
- **F3 (#21)**: `lib/enums.ts`, `lib/format.ts`, `components/data/*`.
- **F6 (#22)**: trace explorer (waterfall, inspector, raw events, input/output, anomaly strip) and `/traces`.
- **F5 (#24)**: executions table with URL-synced filters.
- **F4 (#23)**: overview.
- Checks at last commit: `npm run typecheck`, `npm run lint`, `npm run build` clean; `npm test` 134 passing.

## In progress
- nothing mid-edit.

## Next up
1. F7 (#25) agents list + detail → F8 (#26) anomalies → F9 (#27) investigations (report view, trigger + poll; the trace header's Investigate button already links to `/investigations/[executionId]`).
2. F12 (#28) live pass as soon as a backend is reachable: start with `/health`, `/agents`, `/executions`, `/executions/{id}/trace`, `/executions/{id}/events`, `/stats/*`, `/anomalies`.
3. F13 (#29): Playwright smoke of the demo path (needs `npx playwright install chromium`, a download). Vitest side is already at 134 tests.
4. F10 (#30) replay dialog + comparison (the trace header's Replay button is disabled and says so), F11 (#31) settings.
5. Frontend CI job, once `.github/workflows/ci.yml` is on `main`: `npm ci && npm run typecheck && npm run lint && npm test && npm run build && npm run validate-fixtures`.
6. After X1 merges: merge `main` into `adit/frontend` (the fixtures are already here via a merge of `contract/fixtures`, so it should be a no-op).

## Waiting on backend (endpoint → why)
Per `backend/PROGRESS.md` on `origin/jayden/backend` (e9f4c53) everything except the below is implemented.
- POST /executions/{id}/replay, /replays* (B12, B13) → replay UI stays on mocks
- PATCH /anomalies/{id} (P1) → the hook exists; no UI calls it yet
- cost_usd (B14) → null until then; shown as "—"
- `jayden/backend` → `main` → needed before the frontend CI job can be filled

## Environment (this machine: Windows 11)
- node 24.19, npm 11.17, git 2.55, uv 0.12, python 3.12, gh 2.104 (logged in as adituppal7): OK
- docker: MISSING → cannot run the backend + Postgres here; the live pass needs Docker Desktop or a URL to Jayden's backend
- Playwright browsers not installed
- `.claude/launch.json` (local, git-excluded) starts the dev server for the in-app browser

## Decisions
- **Fixtures are generated** by `scripts/build-fixtures.ts` from `scripts/fixtures/story.ts` (events → steps → executions → anomalies → investigations → stats), porting the backend's anomaly and report templates. After X1 merges, run it only on a `contract/<topic>` branch. Scenario index: `contract/fixtures/README.md`.
- **Mode is global, never mixed**; anything but `NEXT_PUBLIC_API_MODE=live` is mock. `client.ts` loads the adapter lazily, so a live build does not ship fixtures.
- **`mocks/fixtures/` is generated and git-ignored**; `sync-fixtures` runs before dev, build, typecheck and test.
- **The mock adapter is an in-memory backend**, not a file server: it filters/sorts/paginates, computes stats from the executions (a test asserts they equal the stats fixtures), steps a started investigation through queued → running → completed, and keeps a `pending` replay pending (no worker exists in mock mode). POST investigation on a run with no recorded report answers `bad_request` rather than inventing one.
- **Mock keeps a running execution "now"**: its timestamps are shifted so its latest event is 2 s old. Nothing else in the fixtures moves.
- **Debug states** (mock only): `?__state=empty | error | large` (large = 250 generated steps on any trace).
- **Polling**: trace 3 s while running; investigation 2 s while queued/running; replay 2 s until terminal; lists and overview panels 5 s (`LIST_POLL_MS`) so a demo run appears without a reload.
- **Queries do not retry silently**; errors show the API's message, code and a Retry button.
- **URL state** uses `history.replaceState/pushState` (`lib/use-url-state.ts`), which Next's router observes. Trace: `?step`, `?tab`, `?detail`, `?anomaly`, `?event`. Executions: the contract's own param names plus `range` (rolling 1h/24h/7d/30d, resolved at request time). Overview: `?window`.
- **Attempt badge is `n/N`** ("attempt 2 of 3") on each attempt's row, instead of one `×3` badge, because each attempt is its own step.
- **Tree depth is derived from `parent_step_id`**, as the backend derives `depth`; a step with an unknown or looping parent is a root.
- **The waterfall axis spans the execution's duration**, stretched to cover every recorded step; for a running execution it spans up to the browser's clock.
- **Completed bars are neutral grey**; only failed (red) and running (blue, striped) carry colour.
- **Evidence links**: step → `/executions/{id}?step=`, event → `?tab=events&event=`, execution → `/executions/{ref}`, anomaly → `/anomalies?anomaly=`.
- **Table columns** Error, Steps and Cost drop below 1400/1280 px so the table never scrolls sideways at 1024.
- **Overview "Open anomalies" and "Agents" tiles are current totals**, not windowed (backend decision); the tile says so.
- **Tertiary text is `#8A8A93`** (the brief's `#71717A` is 4.1:1). Dark only. JSON syntax colours are desaturated.
- **Next 16 `cacheComponents`**: anything reading the URL sits in `<Suspense>`; dynamic pages pass `params` into Suspense.
- **`@types/node` is ^24** (vitest 5 requires ≥22); `@vitejs/plugin-react` is not used (peer conflict with shadcn's babel 7; vitest's built-in JSX transform is enough).
- GET /investigations/{execution_id} 404 = "no investigation yet" (`useInvestigation` returns `null`). Raw-event item type is `StoredEvent`.
- Git identity for this clone: `adituppal7` with the GitHub noreply address (repo-local).

## Contract change requests (open)
- none

## Known issues
- Not measured: scrolling frame rate with 250 steps (the in-app browser pane was hidden, which throttles rendering). Virtualisation is confirmed: 33 of 250 rows are in the DOM.
- Visual checks at 1440 px were done by layout metrics and partial screenshots only; the pane shows about 800–1024 px.
- Agent names link to `/agents/[id]`, which 404s until F7.
- The palette searches pages only; execution/agent lookup is not built.
- Kickoff said anomalies and investigations are not built; Jayden's branch says they are. Confirm at the first live pass.
- `token_spike` fixture shows "387× above baseline": correct for a >64 KB payload, but dramatic.
- Issues #2 and #19–#31 have no assignee.

## How to run
- `cd frontend && npm i && npm run dev` (mock mode by default; no env file needed)
- Live: create `frontend/.env.local` with `NEXT_PUBLIC_API_MODE=live` and `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`
- Checks: `npm run typecheck && npm run lint && npm test && npm run build && npm run validate-fixtures`
