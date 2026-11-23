# Ghostwatch: rules for every Claude session in this repo

Ghostwatch is an observability and reliability platform for AI agents, built by two developers in 48 hours. Two separate Claude sessions work on this repo in parallel: one for Jayden (backend/SDK/demo) and one for Adit (frontend). They cannot see each other's conversations. The repo, the contract and the PROGRESS files are the only shared memory, so keep them accurate.

## Read before doing anything
1. `contract/API_CONTRACT.md`: the frozen API contract. If code and contract disagree, the code is wrong.
2. `PROJECT_PLAN.md`: architecture, ownership, issues, schedule, definition of done.
3. Your side's `PROGRESS.md` (`backend/PROGRESS.md` or `frontend/PROGRESS.md`): where the last session left off.
4. `docs/PRODUCT_SPEC.md`: the original brief, for intent.

## Ownership (enforced by CODEOWNERS; do not cross it)
- Jayden's Claude writes only: `backend/`, `sdk/`, `demo/`, `docker-compose.yml`, `docs/API.md`, the BACKEND section of `.env.example`, the backend job in `.github/workflows/ci.yml`.
- Adit's Claude writes only: `frontend/`, the FRONTEND section of `.env.example`, the frontend job in `.github/workflows/ci.yml`.
- One exception: for issue X1, Adit's Claude authors `contract/fixtures/` once, on a `contract/fixtures` branch that Jayden reviews. After that PR merges, fixtures follow the contract-change process like everything else in `contract/`.
- Otherwise, nobody's Claude edits `contract/`, `PROJECT_PLAN.md`, `CLAUDE.md`, `CONTRIBUTING.md` or `.github/CODEOWNERS` on its own. If one of these needs to change, stop and write a Contract Change Request (format in `CONTRIBUTING.md`) for your human to raise with the other developer.
- Reading anything anywhere is always fine and encouraged.

## Non-negotiables
- **Never fabricate.** No fake metrics, no hard-coded "realistic" numbers in live mode, no placeholder evidence. If something isn't implemented, the UI says "Not implemented" and the API returns an honest error.
- **Facts vs hypotheses.** Deterministic code produces facts and evidence. The LLM only proposes hypotheses that cite those facts. Only the deterministic signature matcher can mark a root cause `confirmed`.
- **Replay is sandboxed by default.** No side-effecting tool ever runs during a sandbox replay. Live replay requires explicit `authorize_side_effects: true`.
- **Secrets:** never commit `.env`, keys or credentials. Use `.env.example` with placeholder values.
- **Scope:** finish P0 before P1 and P1 before P2 (see `PROJECT_PLAN.md` §7). No Kubernetes, microservices, Redis/Celery or extra infrastructure.

## Git
- Work on your branch (`jayden/backend` or `adit/frontend`, or `feature/<owner>-<topic>` cut from it). Never commit directly to `main`.
- Small, frequent commits in Conventional Commit style: `feat(ingest): derive steps from step.* events`. Reference the issue: `Refs #12`.
- Run the relevant tests before every commit. Never say tests pass unless you ran them in this session and saw them pass.
- Pull/rebase from `main` before starting a new task.

## Working style
- Investigate before you change: open and read the files involved before editing them. Never guess at an API, a library signature or the contents of a file you haven't read.
- Prefer the simplest design that satisfies the contract and the definition of done. Don't add abstractions, config options or files the task doesn't need.
- Write general, correct implementations. Never special-case a test or a demo scenario to make it pass.
- At the end of every task, update your `PROGRESS.md` (format is in your kickoff prompt) so a fresh session or the other developer can pick up instantly.

## Session handoff (`.claude/state/handoff-frontend.md`, `.claude/state/handoff-backend.md`)
- Each side has its own file: `handoff-frontend.md` for Adit's session, `handoff-backend.md` for Jayden's. Write only your own side's file.
- The SessionStart hook picks it from the branch: `adit/` and `feature/adit-` load the frontend file, `jayden/` and `feature/jayden-` the backend file. Any other branch loads both.
- Update it before any compact, and whenever a significant decision is made or something is declined.
- It holds: decisions and the reasoning behind them, work left half-finished, what was explicitly declined, and the next concrete step.
- Keep it under 20 lines. Replace stale lines instead of appending.
- Write lines that stay true: "verify X completed" rather than "X is running"; name commits and files rather than "just now".
- It is committed: commit it alongside the work it describes, so the reasoning stays in history. Status the other developer or a fresh clone needs still belongs in your `PROGRESS.md`.
- The repo is public, so a handoff file must contain no secrets and no personal details.
- `.claude/state/snapshot.md` is written by a hook and is git-ignored; never edit it by hand.
