# Frontend progress — updated 2026-11-14T20:30Z

## Status: X1 fixtures are written, validated and committed locally but NOT pushed (no GitHub credentials on this machine). F1 scaffold and shell build clean but have not been looked at in a browser yet. F2 not started.

## Pages (mock ✓ / live ✓)
All eight top-level routes render the app shell with a labelled "Not implemented" placeholder.
- Overview `/`: mock ✗ live ✗
- Agents `/agents`, `/agents/[id]`: mock ✗ live ✗
- Executions `/executions`: mock ✗ live ✗
- Trace explorer `/executions/[id]`: mock ✗ live ✗ (route not created yet)
- Traces `/traces`: mock ✗ live ✗
- Anomalies `/anomalies`: mock ✗ live ✗
- Investigations `/investigations`, `/investigations/[executionId]`: mock ✗ live ✗
- Replays `/replays`, `/replays/[id]` (P1): mock ✗ live ✗
- Settings `/settings` (P1): mock ✗ live ✗

## Done
- F1a (#19): `create-next-app` scaffold: Next 16.4, React 19, TS strict, Tailwind 4, ESLint.
- `lib/api/types.ts`: mirror of contract v1.1, enum value lists exported as constants.
- X1 (#2): 144 fixtures in `contract/fixtures/` + `README.md` index. Commit `b391bae` on local branch `contract/fixtures` (cut from `main`, touches only `contract/fixtures/`), also merged into `adit/frontend`.
  - `npm run validate-fixtures`: 144 fixtures match types, 571 ids / 1048 references resolve, 19 enums fully covered.
  - Jayden's `tests/test_conformance.py -k fixture` at e9f4c53 with these fixtures: 145 passed.
- F1b (#19): design tokens in `app/globals.css`, Geist fonts (local `geist` package), shadcn/ui (radix, nova preset), sidebar, breadcrumbs, MOCK DATA badge, Ctrl/⌘K palette (pages only), `Page`, `EmptyState`, `NotImplemented`. `tsc`, `eslint` and `next build` pass.

## In progress
- F1b verification: load every route in the browser at 1440 and 1024 px. `.claude/launch.json` (local, git-excluded) starts the dev server.

## Next up
1. **Push `contract/fixtures` and open the X1 PR** to `main` once `gh auth login` is done. PR body is drafted (not in the repo); title `[X1] Contract fixtures for every endpoint`.
2. Finish F1b verification; fill the frontend CI job when `ci.yml` reaches `main`.
3. F2 (#20): `client.ts`, `mock.ts`, `live.ts`, `hooks.ts`, `npm run sync-fixtures`.
4. F3 (#21) → F6 (#22) → F4 (#23) → F5 (#24) → live pass (#28) → F7 → F8 → F9 → F13 → F10 → F11.

## Waiting on backend (endpoint → why)
Per `backend/PROGRESS.md` on `origin/jayden/backend` (e9f4c53) everything except the below is implemented.
- POST /executions/{id}/replay, /replays* (B12, B13) → replay UI stays on mocks
- PATCH /anomalies/{id} (P1) → acknowledge/resolve stay "Not implemented"
- cost_usd (B14) → null until then
- `jayden/backend` → `main` → needed before the frontend CI job can be filled (`ci.yml` exists only on his branch)

## Environment (this machine: Windows 11)
- node 24.19, npm 11.17, git 2.55, uv 0.12, python 3.12: OK
- gh 2.104 installed at `C:\Program Files\GitHub CLI` but **not logged in**; git has no GitHub credentials → cannot push
- docker: MISSING → cannot run the backend + Postgres locally for the live switch
- Playwright browsers not installed (needed for F13)
- A read-only checkout of `jayden/backend` with a uv venv was made in a temp folder to run conformance; it may be gone after a reboot (`git worktree prune` cleans the reference).

## Decisions
- **Fixtures are generated**, not hand-written: `scripts/build-fixtures.ts` builds one world from `scripts/fixtures/story.ts` and derives events → steps → executions → anomalies → investigations → stats, so files cannot disagree. Anomaly and investigation text ports the backend's templates (`rules.py`, `facts.py`, `signatures.py`). After X1 merges, run it only on a `contract/<topic>` branch.
- **Fixture world**: 5 agents (3 demo agents, `ticket-digest` scheduled job, idle `pr-reviewer`), 41 executions, fixture clock `2026-11-14T18:00:00.000Z`. Every execution has a trace and an events file named by execution id. Scenario index: `contract/fixtures/README.md`.
- **Not produced by the backend today but present in fixtures** (listed in the fixtures README): evidence kinds `event` and `metric`; `cost_usd` values from a fixture-only price; anomaly statuses `acknowledged`/`resolved`; replay comparisons computed from the contract's outcome rule.
- **Health fixture says `rule_based`**; the one `fable` report (`probable`) records its own provider and model.
- **Manual investigation fixtures** (`investigations.create`, `.get.queued`, `.get.running`, `.get.manual_result`) belong to the `rate_limit` run and are not in `investigations.list.json`; the mock adapter will step through them after a POST.
- **Mode is global, never mixed.** Anything other than `NEXT_PUBLIC_API_MODE=live` is mock, so a missing variable cannot show fixtures unlabelled.
- **Tertiary text is `#8A8A93`**, not the brief's `#71717A`, which is 4.1:1 on the background.
- **Dark only**: `class="dark"` on `<html>`; shadcn variables are mapped onto the Ghostwatch tokens.
- **Next 16 has `cacheComponents` on**: anything reading the URL (`usePathname`, `useSearchParams`, `params`) sits inside `<Suspense>`; no `Date.now()` during prerender.
- **Queries do not retry silently** (`retry: false`): errors show with a Retry button.
- GET /investigations/{execution_id} 404 = "no investigation yet". Raw-event item type is `StoredEvent`. Settings shows the mode read-only.
- Git identity for this clone: `adituppal7` with the GitHub noreply address (repo-local).

## Contract change requests (open)
- none

## Known issues
- X1 is not on GitHub yet; Jayden is still blocked on it.
- Kickoff said anomalies and investigations are not built; Jayden's branch says they are. Confirm at the first live pass.
- The palette searches pages only; execution and agent lookup comes with F2.
- `token_spike` fixture shows "387× above baseline": correct for a >64 KB payload, but dramatic.
- Issues #2 and #19–#31 have no assignee.

## How to run
- `cd frontend && npm i && npm run dev` (mock mode by default; no env file needed)
- Live: create `frontend/.env.local` with `NEXT_PUBLIC_API_MODE=live` and `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`
- Checks: `npm run typecheck && npm run lint && npm run build && npm run validate-fixtures`
