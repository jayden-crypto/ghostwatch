# Handoff — Adit's frontend session (committed, frontend side only; durable status is in frontend/PROGRESS.md)

- `main` has the whole frontend: PR 38 (F1–F11, F13, b36be58) and PR 39 (query results by microtask, fe86776). `adit/frontend` is `main` merged back (7e19a1f). Read `frontend/PROGRESS.md` first.
- Left in F12 (#28): Jayden's session checked lists, filters across reloads and ack/resolve/reopen on a production build (`docs/DEMO_SCRIPT.md`, PR 40 merged as 4ac9ad6); its "Not checked" list is what remains. No Docker here.
- Fixed (2026-11-22, on `adit/frontend`, not on `main` yet): [id] pages stayed empty in a pane that draws no frames, because React reveals server-streamed content on requestAnimationFrame. They now read the id with `useParams()` (`TraceRoute` etc.); `e2e/no-frames.spec.ts` guards it. Jayden's 2026-11-17 "request already 200" case is still unexplained.
- 2026-11-19: Adit confirmed contract v1.1 and v1.2 to Jayden in writing.
- Never merge to `main`, force-push, open PRs or post reviews without Adit's OK.
- Decisions: settings is read-only (config is build-time); components never read `API_MODE` (the /settings route passes it as props); replay wording lives in `frontend/lib/replay.ts` (contract v1.2 text).
- Handoff per side: PR 41 merged (8d71898). Never write `handoff-backend.md` from here. Jayden asked for a CLAUDE.md line: the repo is public, so no secrets or personal details in handoffs (needs a PR he approves).
- In e2e tests click the visible card or label, never force-click an sr-only input (fails on Linux Chromium).
- Not verified: the hooks running through Claude Code's own hook runner on Windows; only the settings.json commands were run under Git Bash. Jayden ran save-state.sh on macOS: works.
- Windows quirks: patch scripts go in the scratchpad, not long heredocs; Write may leave CRLF, so multi-line string patches can miss (use Edit); `gh` needs `export PATH="$PATH:/c/Program Files/GitHub CLI"`.
