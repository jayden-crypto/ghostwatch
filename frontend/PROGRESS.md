# Frontend progress — updated 2026-11-18T14:30Z

## Status: every frontend page is built and verified in mock mode (F1–F11, F13), and the frontend CI job is filled in. The backend, SDK and demo are on `main` (PR #36, merged) and merged into `adit/frontend`. PR #37 (UTF-8 file reads) is merged, and `main` at 8377e7f is merged into `adit/frontend`. PR #38 (F1–F11 and F13) was approved by Jayden and squash-merged to `main` as b36be58, and `main` is merged back into `adit/frontend`. PR #39 (query results delivered by microtask, below) was approved by Jayden and squash-merged as fe86776; `main` is merged back again. Jayden reports running the demo script with `main`'s frontend in live mode against a scratch backend (macOS, Chromium, dev server): every step worked, with no console errors and no unexpected API errors. Not run in this session. Not covered by that run: list pages, filters, ack/resolve, a production build. Nothing has been run against a live backend on this machine (no Docker). F12 stays open for those.

## Pages (mock ✓ / live ✓)
- Overview `/`: mock ✓ live ✗ (untested)
- Agents `/agents`, `/agents/[id]`: mock ✓ live ✗ (untested)
- Executions `/executions`: mock ✓ live ✗ (untested)
- Trace explorer `/executions/[id]` (tabs: Waterfall, Raw events, Input & output, Investigation): mock ✓ live ✗ (untested)
- Traces `/traces`: mock ✓ live ✗ (untested)
- Anomalies `/anomalies`: mock ✓ live ✗ (untested)
- Investigations `/investigations`, `/investigations/[executionId]`: mock ✓ live ✗ (untested)
- Replays `/replays`, `/replays/[id]`, and the Replay dialog on the trace page (P1): mock ✓ live ✗ (untested)
- Settings `/settings` (P1): mock ✓ live ✗ (untested)
- `/dev/components`: every enum badge and shared state on one page (not in the nav)

## Done
- **X1 (#2)**: PR https://github.com/jayden-crypto/ghostwatch/pull/35, merged to `main` as 36e3390. Passes `npm run validate-fixtures` and Jayden's `tests/test_conformance.py -k fixture` at cd7261e (145 passed); all 41 trace costs equal `app.services.pricing.execution_cost`.
- **Review of PR #36** (`jayden/backend` → `main`) at 2b3e4ec: approved with comments on 2026-11-16. One bug reported for a follow-up: `read_text()` without `encoding="utf-8"` makes three tests in `backend/tests/test_openapi.py` fail on Windows (same pattern in `backend/tests/test_demo_e2e.py:332` and `demo/settings.py:14`). Local run on Windows: ruff clean, SDK 39 passed, backend 386 passed / 209 skipped (no Postgres) / 3 failed (the encoding). Behaviours the frontend relies on, read from the code: `limit > 200` → 422, `/stats/timeseries` with an unknown `agent_id` → 404, list filters accept comma lists, `POST /investigations/{id}` answers 200 or 202.
- **F1–F6, F4, F5** as before; **F7 (#25)** agents list + detail; **F8 (#26)** anomalies; **F9 (#27)** investigation report, list, trigger + poll, and the trace page's Investigation tab.
- **F13 (#29)**: Playwright smoke tests in `e2e/` (`npm run test:e2e`): the demo path (overview → failed run → confirmed investigation → evidence link → failing step selected), the replay path (failed run → its replays → comparison "Fixed" → replay step in the replay's trace), and the dialog (live needs the authorization box; sandbox request lands on the pending page). They build the app and serve it on port 3100 in mock mode; Edge on Windows, Playwright's Chromium elsewhere.
- **F10 (#30)**: Replay dialog (`components/replay/replay-dialog.tsx`), list (`replays-view.tsx`), replay page and comparison (`replay-view.tsx`, `replay-comparison.tsx`), shared wording in `lib/replay.ts`.
- **F11 (#31)**: settings page (`components/settings/settings-view.tsx`): data source, backend health and investigation provider from `GET /health`, access note. Read-only.
- **Frontend CI job** in `.github/workflows/ci.yml`: `npm ci`, typecheck, lint, unit tests, fixture validation, then Playwright's Chromium and the e2e tests. Green on Linux at 5328cf4 (run 43909550469: 191 unit tests, 3 e2e). The first run failed one e2e test: Linux Chromium refuses a forced click on a visually hidden radio, so the test now clicks the card.
- **Review of PR #37** (`jayden/backend` → `main`, 83e49cb, "read and write text files as UTF-8"), approved on 2026-11-16: on this Windows machine with the default cp1252 encoding, backend 389 passed / 209 skipped (no Postgres) / 0 failed, also with `PYTHONWARNDEFAULTENCODING=1`; SDK 39 passed; ruff clean; `alembic upgrade head --sql` runs. No other unencoded file read or write found in `backend/`, `sdk/`, `demo/`. `tests/test_fable_provider.py` was left out only because the scratch checkout's path is too long for Windows.
- **Contract v1.2** in `types.ts` (`ReplaySource`, `StepDiff.replay_source`); a replay step's source is shown in the waterfall and the inspector.
- Checks at last commit: `npm run typecheck`, `npm run lint`, `npm run validate-fixtures` clean; `npm test` 191 passing; `npm run test:e2e` 3 passing (it runs `npm run build` first).

## In progress
- nothing mid-edit.

## Next up
1. A separate small PR for one committed handoff per side (below).
2. F12 (#28) live pass as soon as a backend is reachable. First calls: `/health`, `/agents`, `/executions`, `/executions/{id}/trace`, `/executions/{id}/events`, `/stats/overview`, `/stats/timeseries`, `/anomalies`, `/investigations`. Then `PATCH /anomalies/{id}` and `POST /investigations/{id}`.
3. Live checks for replays in F12: `POST /executions/{id}/replay` (sandbox; live without the box must be impossible from the UI), `GET /replays`, `GET /replays/{id}` while a worker runs (`cd demo && uv run python replay.py worker --fixed`), and the 409 for a running execution.

## Waiting on backend (endpoint → why)
Per `backend/PROGRESS.md` on `origin/jayden/backend` (cd7261e) every contract endpoint is implemented, including replays (B12, B13), cost (B14) and `PATCH /anomalies/{id}`.
- Nothing is missing on the backend side. The live pass needs a running backend: Docker Desktop here, or a URL to Jayden's.
- Contract v1.1 and v1.2 were committed to `main` by Jayden with "Adit to confirm" → the PR #36 review says the frontend has no objection and already follows v1.2; Adit has not given Jayden an explicit confirmation himself

## Environment (this machine: Windows 11)
- node 24.19, npm 11.17, git 2.55, uv 0.12, python 3.12, gh 2.104 (logged in as adituppal7; not on Git Bash's PATH, it is in `C:\Program Files\GitHub CLI`): OK
- docker: MISSING → cannot run the backend + Postgres here; the live pass needs Docker Desktop or a URL to Jayden's backend
- `@playwright/test` 1.65 is installed; it drives the installed Edge, so no browser download was needed here
- `.claude/launch.json` (local, git-excluded) starts the dev server for the in-app browser
- `git config core.safecrlf false` is set locally to silence line-ending warnings on the generated fixtures

## Decisions
- **Fixtures are generated** by `scripts/build-fixtures.ts` from `scripts/fixtures/story.ts`, porting the backend's anomaly, report, replay-source and pricing rules. The generator refuses a replay that breaks the sandbox rule. Regenerate only on a `contract/<topic>` branch; the X1 branch is checked out as a separate git worktree when needed, so `adit/frontend` never has to be switched away.
- **Replay dialog**: Sandbox is preselected and described with the v1.2 wording (`SANDBOX_RULE` in `lib/replay.ts`). Choosing Live shows the checkbox "I authorize real external side effects for this replay"; the submit button is disabled until it is ticked, and the tick is forgotten when the mode changes. A live request sends `authorize_side_effects: true`; a sandbox request does not send the field. A refusal from the API is shown with its message, code and HTTP status. The button is disabled for a running execution (the backend answers 409). After a successful request the app goes to `/replays/{id}`.
- **Replay page**: pending says a replay worker must pick it up and shows the worker command; claimed says a worker is running it; failed is worded as a failure to run the replay, not a result; completed shows the comparison. Polls every 2 s until terminal.
- **Comparison**: the outcome is the headline (`fixed` is the only filled green frame; `inconclusive` is dashed). Under it, a sentence counts the replay's steps by `replay_source` (the only thing computed in the browser), then the mode's rule. Original and replay are one table with the API's three deltas; a null delta is a dash. The step table marks rows whose `change` is not `unchanged`, links each side to its own step, and shows `replay_source` per row.
- **Replays list**: `?status=` and `?original_execution_id=` in the URL (the trace header's "Replayed N×" links there). A replay without a comparison says "Not compared yet"; a failed one shows its error type.
- **Mock replays**: a replay created in mock mode stays pending (there is no worker); pending and claimed fixture replays are moved to "now" like a running execution; replaying a running execution answers `conflict` as the backend does.
- **Settings is read-only.** The mode and base URL are fixed at build time, so the page shows them and says how to change them (`frontend/.env.local`, restart). The route passes `API_MODE` and `API_BASE_URL` to the view as props; components still never read the config. In mock mode the health panels say the values are the `health.get` fixture. A failed health check shows the API's error and, in live mode, the commands that start the backend; the provider is then "not known" rather than guessed. `llm_provider: fable` with `llm_configured: false` is shown as "No: not configured". Health is re-checked every 5 s and on "Check again".
- **Mode is global, never mixed**; anything but `NEXT_PUBLIC_API_MODE=live` is mock. `client.ts` loads the adapter lazily.
- **The mock adapter is an in-memory backend**: filters/sorts/paginates, computes stats, applies `PATCH /anomalies`, steps a started investigation through queued → running → completed (4 s, starting "now"), keeps a `pending` replay pending. POST investigation on a run with no recorded report answers `bad_request` rather than inventing one.
- **Mock keeps a running execution "now"**; debug states `?__state=empty | error | large`.
- **Query results reach components through a microtask** (`notifyManager.setScheduler(queueMicrotask)` in `components/shell/providers.tsx`), not TanStack's default `setTimeout(0)`, so a finished request no longer waits for a timer. Browsers throttle timers in a hidden page.
  - Measured here on the trace page (live-mode dev server, API stubbed from fixtures) with every timer forced to the next 5 s boundary: trace response → first step row went from ~4.6 s to ~45 ms. A really hidden page could not be reproduced under Playwright (it always reports `visible`).
  - Raised by Jayden: pages sometimes sat on the skeleton 5–20 s after a 200 while his browser pane was hidden. Whether this was the cause is **not confirmed**. One throttled timer is usually ~1 s, and a dev server compiles routes on first visit. He needs to re-run with the pane hidden, ideally on a production build.
  - Guarded by `tests/components/providers.test.tsx`. Still on timers in a hidden page, which is fine: polling intervals, and the "N s elapsed" text of a pending investigation or replay (shows "…" until its first tick).
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
- **Committed session handoff, one file per side**, agreed by Jayden in his PR #38 review (2026-11-17). The shared-file version (03ed770) was reverted in 629b0d1, so `.claude/state/` is git-ignored again and `CLAUDE.md` is back to its old wording. Still to do, in its own PR (#38 is merged):
  - commit `.claude/state/handoff-frontend.md` and `handoff-backend.md`;
  - make `rehydrate.sh` pick the file from the branch prefix (`adit/` or `jayden/`);
  - change `.gitignore` (keep `snapshot.md` ignored) and the Session handoff section of `CLAUDE.md`. Those files need both developers' agreement.
  - `.claude/hooks/save-state.sh` fixes d55941d and c619052 stay; Jayden ran them on macOS and they work.
- Open item from the backend side: contract v1.1 and v1.2 await Adit's explicit confirmation.

## Known issues
- Not measured: scrolling frame rate with 250 steps (the in-app browser pane was hidden). Virtualisation is confirmed: 33 of 250 rows are in the DOM.
- The replay screens were looked at by eye at 1440 and 1024 px. The older pages were checked at about 1024 px, mostly through DOM and layout checks; they have not been looked at by eye at 1440 px.
- A replay execution's trace says "Replay of <original>" but cannot link to its comparison: `ExecutionDetail` has no replay id. The comparison is reachable from the original's "Replayed N×" link and from `/replays`.
- In a table whose rows are links (replays, investigations), the id chips sit on top of the row link, so a click in the middle of a row can land on an id. Intended, but the e2e test clicks rows at their left edge because of it.
- The palette searches pages only.
- `token_spike` fixture shows "387× above baseline": correct for a >64 KB payload, but dramatic.
- Issues #2 and #19–#31 have no assignee.

## How to run
- `cd frontend && npm i && npm run dev` (mock mode by default; no env file needed)
- Live: create `frontend/.env.local` with `NEXT_PUBLIC_API_MODE=live` and `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`
- Checks: `npm run typecheck && npm run lint && npm test && npm run validate-fixtures && npm run test:e2e`
