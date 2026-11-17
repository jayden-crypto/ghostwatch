# Handoff — Adit's frontend session (committed; durable status is in frontend/PROGRESS.md)

- Branch `adit/frontend`, with `main` at 8377e7f (PRs 35, 36, 37) merged in. Read `frontend/PROGRESS.md` first.
- Built and verified in mock mode only: F1–F11, F13. Left: F12 live pass (needs Docker or a backend URL; none on Adit's machine).
- Frontend CI job is green on Linux at 5328cf4. In e2e tests click the visible card or label, never force-click an sr-only input (fails on Linux Chromium).
- Adit has not given Jayden an explicit confirmation of contract v1.1 and v1.2. Do not confirm on his behalf.
- Never merge to `main`, force-push, open PRs or post reviews without Adit's OK. PR 36 and 37 approvals were posted only after he said so.
- Decisions: settings is read-only (config is build-time); components never read `API_MODE` (the /settings route passes it as props); replay wording lives in `frontend/lib/replay.ts` (contract v1.2 text).
- 2026-11-17, Adit decided: this file is committed, and `.gitignore` ignores only `snapshot.md`. Claude advised against it (two sessions share one path) and Adit chose it anyway. CLAUDE.md's handoff section was edited to match, at his request.
- Open: Adit to forward the change request for that CLAUDE.md/.gitignore change to Jayden. Before Jayden next merges `main`, he must copy his local `.claude/state/handoff.md` aside: the merge silently replaces it (tested). Verify he has answered before building on this.
- Not verified: the hooks running through Claude Code's own hook runner on Windows; only the settings.json commands were run under Git Bash.
- Windows quirks: patch scripts go in the scratchpad, not long heredocs; Write may leave CRLF, so multi-line string patches can miss (use Edit); `gh` needs `export PATH="$PATH:/c/Program Files/GitHub CLI"`.
