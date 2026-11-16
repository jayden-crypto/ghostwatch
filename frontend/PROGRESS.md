# Frontend progress — updated 2026-11-16T15:40Z

## Status: all P0 pages are built and verified in mock mode (F1–F9). X1 PR #35 is merged to `main` and `main` is merged back into `adit/frontend` (no file changes). Jayden's backend PR #36 is reviewed and approved by Adit (not merged yet). Nothing has been run against the live backend yet (no Docker on this machine). F13's Playwright smoke test, F10 and F11 are not started.

## Pages (mock ✓ / live ✓)
- Overview `/`: mock ✓ live ✗ (untested)
- Agents `/agents`, `/agents/[id]`: mock ✓ live ✗ (untested)
- Executions `/executions`: mock ✓ live ✗ (untested)
- Trace explorer `/executions/[id]` (tabs: Waterfall, Raw events, Input & output, Investigation): mock ✓ live ✗ (untested)
- Traces `/traces`: mock ✓ live ✗ (untested)
- Anomalies `/anomalies`: mock ✓ live ✗ (untested)
- Investigations `/investigations`, `/investigations/[executionId]`: mock ✓ live ✗ (untested)
- Replays `/replays` (P1): placeholder; `/replays/[id]` has no route yet, so "Replayed N×" on a trace leads to the placeholder list
- Settings `/settings` (P1): placeholder
- `/dev/components`: every enum badge and shared state on one page (not in the nav)

## Done
- **X1 (#2)**: PR https://github.com/jayden-crypto/ghostwatch/pull/35, merged to `main` as 36e3390. Passes `npm run validate-fixtures` and Jayden's `tests/test_conformance.py -k fixture` at cd7261e (145 passed); all 41 trace costs equal `app.services.pricing.execution_cost`.
- **Review of PR #36** (`jayden/backend` → `main`) at 2b3e4ec: approved with comments on 2026-11-16. One bug reported for a follow-up: `read_text()` without `encoding="utf-8"` makes three tests in `backend/tests/test_openapi.py` fail on Windows (same pattern in `backend/tests/test_demo_e2e.py:332` and `demo/settings.py:14`). Local run on Windows: ruff clean, SDK 39 passed, backend 386 passed / 209 skipped (no Postgres) / 3 failed (the encoding). Behaviours the frontend relies on, read from the code: `limit > 200` → 422, `/stats/timeseries` with an unknown `agent_id` → 404, list filters accept comma lists, `POST /investigations/{id}` answers 200 or 202.
- **F1–F6, F4, F5** as before; **F7 (#25)** agents list + detail; **F8 (#26)** anomalies; **F9 (#27)** investigation report, list, trigger + poll, and the trace page's Investigation tab.
- **Contract v1.2** in `types.ts` (`ReplaySource`, `StepDiff.replay_source`); a replay step's source is shown in the waterfall and the inspector.
- Checks at last commit: `npm run typecheck`, `npm run lint`, `npm run build` clean; `npm test` 161 passing.

## In progress
- nothing mid-edit.

## Next up
1. After PR #36 merges: merge `main` into `adit/frontend` again. It brings `.claude/settings.json` and two session hooks (read-only, reviewed), a "Session handoff" section in `CLAUDE.md`, `README.md` and `.github/workflows/ci.yml`.
2. F12 (#28) live pass as soon as a backend is reachable. First calls: `/health`, `/agents`, `/executions`, `/executions/{id}/trace`, `/executions/{id}/events`, `/stats/overview`, `/stats/timeseries`, `/anomalies`, `/investigations`. Then `PATCH /anomalies/{id}` and `POST /investigations/{id}`.
3. F13 (#29): Playwright smoke of the demo path in mock mode (overview → failed execution → investigation → evidence link → step highlighted). Needs `@playwright/test`; can run on the installed Edge (`channel: "msedge"`) so no browser download is needed.
4. F10 (#30) replay dialog, list and comparison (backend B12/B13 are built now). Dialog copy must be the v1.2 wording from commit 4b7568d, not the kickoff's.
5. F11 (#31) settings.
6. Frontend CI job, once `.github/workflows/ci.yml` is on `main`: `npm ci && npm run typecheck && npm run lint && npm test && npm run build && npm run validate-fixtures`.

## Waiting on backend (endpoint → why)
Per `backend/PROGRESS.md` on `origin/jayden/backend` (cd7261e) every contract endpoint is implemented, including replays (B12, B13), cost (B14) and `PATCH /anomalies/{id}`.
- `jayden/backend` → `main` (PR #36, approved, open) → needed before the frontend CI job can be filled (`ci.yml` is only on his branch) and before a clean clone can run the backend
- Contract v1.1 and v1.2 were committed to `main` by Jayden with "Adit to confirm" → the PR #36 review says the frontend has no objection and already follows v1.2; Adit has not given Jayden an explicit confirmation himself

## Environment (this machine: Windows 11)
- node 24.19, npm 11.17, git 2.55, uv 0.12, python 3.12, gh 2.104 (logged in as adituppal7; not on Git Bash's PATH, it is in `C:\Program Files\GitHub CLI`): OK
- docker: MISSING → cannot run the backend + Postgres here; the live pass needs Docker Desktop or a URL to Jayden's backend
- Playwright not installed
- `.claude/launch.json` (local, git-excluded) starts the dev server for the in-app browser
- `git config core.safecrlf false` is set locally to silence line-ending warnings on the generated fixtures

## Decisions
- **Fixtures are generated** by `scripts/build-fixtures.ts` from `scripts/fixtures/story.ts`, porting the backend's anomaly, report, replay-source and pricing rules. The generator refuses a replay that breaks the sandbox rule. Regenerate only on a `contract/<topic>` branch; the X1 branch is checked out as a separate git worktree when needed, so `adit/frontend` never has to be switched away.
- **Mode is global, never mixed**; anything but `NEXT_PUBLIC_API_MODE=live` is mock. `client.ts` loads the adapter lazily.
- **The mock adapter is an in-memory backend**: filters/sorts/paginates, computes stats, applies `PATCH /anomalies`, steps a started investigation through queued → running → completed (4 s, starting "now"), keeps a `pending` replay pending. POST investigation on a run with no recorded report answers `bad_request` rather than inventing one.
- **Mock keeps a running execution "now"**; debug states `?__state=empty | error | large`.
- **Polling**: trace 3 s while running; investigation 2 s while queued/running; replay 2 s until terminal; lists and overview panels 5 s.
- **URL state** via `history.replaceState/pushState` (`lib/use-url-state.ts`). Trace: `?step`, `?tab`, `?detail`, `?anomaly`, `?event`. Executions: the contract's param names plus `range`. Anomalies: `status`, `severity`, `agent_id`, `type`, plus `?anomaly=<id>` to pin one. Agents: `q`, `health`. Overview and agent detail: `?window`.
- **Anomalies page shows open anomalies by default**; acknowledged and resolved are behind the Status filter. Critical anomalies start with their evidence open.
- **Acknowledge / Resolve / Reopen are real** (`PATCH /anomalies/{id}`); an API refusal is shown on the card.
- **Investigation report**: facts are solid cards with filled id chips, hypotheses are dashed cards; the root-cause banner has three treatments (solid green + signature, dashed amber "Hypothesis: not confirmed", neutral "Insufficient evidence"). The hypotheses heading says "generated by <model>" or "rule-based" from `provider`/`model`. Confidence is three segments plus words, never a percentage. A hypothesis that is the confirmed root cause is tagged "Matches signature …".
- **The trace header's Investigate button opens the Investigation tab** of the same page; `/investigations/[executionId]` is the full page (linked from the list).
- **Attempt badge is `n/N`** on each attempt's row. **Tree depth is derived from `parent_step_id`**. **Completed bars are neutral grey.**
- **Evidence links**: step → `/executions/{id}?step=`, event → `?tab=events&event=`, execution → `/executions/{ref}`, anomaly → `/anomalies?anomaly=`.
- **Tables drop low-priority columns** below 1280/1400 px so nothing scrolls sideways at 1024.
- **Tertiary text is `#8A8A93`**. Dark only. **Next 16 `cacheComponents`**: URL readers sit in `<Suspense>`.
- **`@types/node` is ^24**; `@vitejs/plugin-react` is not used.
- GET /investigations/{execution_id} 404 = "no investigation yet". Raw-event item type is `StoredEvent`.

## Contract change requests (open)
- none from the frontend. Open item from the backend side: contract v1.1 and v1.2 await Adit's explicit confirmation.

## Known issues
- Not measured: scrolling frame rate with 250 steps (the in-app browser pane was hidden). Virtualisation is confirmed: 33 of 250 rows are in the DOM.
- Visual checks were done at about 1024 px, mostly through DOM and layout checks; 1440 px has not been looked at by eye.
- The trace header's Replay button is disabled and says "not implemented" (F10).
- The palette searches pages only.
- `token_spike` fixture shows "387× above baseline": correct for a >64 KB payload, but dramatic.
- Issues #2 and #19–#31 have no assignee.

## How to run
- `cd frontend && npm i && npm run dev` (mock mode by default; no env file needed)
- Live: create `frontend/.env.local` with `NEXT_PUBLIC_API_MODE=live` and `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`
- Checks: `npm run typecheck && npm run lint && npm test && npm run build && npm run validate-fixtures`
