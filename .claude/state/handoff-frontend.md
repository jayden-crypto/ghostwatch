# Handoff — Adit's frontend session (committed, frontend side only; durable status is in frontend/PROGRESS.md)

- `main` has the whole frontend: PR 38 (F1–F11, F13, b36be58) and PR 39 (query results by microtask, fe86776). `adit/frontend` is `main` merged back (7e19a1f). Read `frontend/PROGRESS.md` first.
- Left: F12 (#28) live pass. Jayden ran the demo script live; list pages, filters, ack/resolve and a production build are unchecked. No Docker here: needs Jayden, or a URL to his backend.
- PR 39's fix is proven only under simulated timer throttling; the cause of Jayden's 5–20 s skeletons is not confirmed. Verify he re-ran with the pane hidden on a production build.
- 2026-11-19: Adit confirmed contract v1.1 and v1.2 to Jayden in writing.
- Never merge to `main`, force-push, open PRs or post reviews without Adit's OK.
- Decisions: settings is read-only (config is build-time); components never read `API_MODE` (the /settings route passes it as props); replay wording lives in `frontend/lib/replay.ts` (contract v1.2 text).
- Handoff per side (this file), from `feature/adit-handoff-per-side`, agreed by Jayden in the PR 38 review. Jayden's side moves his own local `handoff.md` to `handoff-backend.md`; never write that file from here.
- In e2e tests click the visible card or label, never force-click an sr-only input (fails on Linux Chromium).
- Not verified: the hooks running through Claude Code's own hook runner on Windows; only the settings.json commands were run under Git Bash. Jayden ran save-state.sh on macOS: works.
- Windows quirks: patch scripts go in the scratchpad, not long heredocs; Write may leave CRLF, so multi-line string patches can miss (use Edit); `gh` needs `export PATH="$PATH:/c/Program Files/GitHub CLI"`.
