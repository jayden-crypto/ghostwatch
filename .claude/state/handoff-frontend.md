# Handoff — Adit's frontend session (committed, frontend side only; durable status is in frontend/PROGRESS.md)

- `main` has the whole frontend: PR 38 (F1–F11, F13, b36be58), PR 39 (query results by microtask, fe86776) and PR 43 (id pages read their id in the browser, 847ad44). `adit/frontend` is `main` merged back (c23a7ad). Read `frontend/PROGRESS.md` first.
- Left in F12 (#28): Jayden's session checked lists, filters across reloads and ack/resolve/reopen on a production build (`docs/DEMO_SCRIPT.md`, PR 40 merged as 4ac9ad6); its "Not checked" list is what remains. No Docker here.
- Fixed in PR 43: [id] pages stayed empty in a pane that draws no frames (React reveals server-streamed content on requestAnimationFrame); they now read the id with `useParams()`, guarded by `e2e/no-frames.spec.ts`. Jayden confirmed it hidden on macOS. His 3 non-blocking notes are PROGRESS "Next up" 1. The 2026-11-17 "request already 200" case is still unexplained.
- Open question for Adit: Jayden's side dates the contract confirmation 2026-11-18 UTC; the frontend files say 2026-11-19. Not changed until Adit says which.
- 2026-11-19: Adit confirmed contract v1.1 and v1.2 to Jayden in writing.
- Never merge to `main`, force-push, open PRs or post reviews without Adit's OK.
- Decisions: settings is read-only (config is build-time); components never read `API_MODE` (the /settings route passes it as props); replay wording lives in `frontend/lib/replay.ts` (contract v1.2 text).
- Handoff per side: PR 41 merged (8d71898). Never write `handoff-backend.md` from here. Jayden asked for a CLAUDE.md line: the repo is public, so no secrets or personal details in handoffs (needs a PR he approves).
- In e2e tests click the visible card or label, never force-click an sr-only input (fails on Linux Chromium).
- Not verified: the hooks running through Claude Code's own hook runner on Windows; only the settings.json commands were run under Git Bash. Jayden ran save-state.sh on macOS: works.
- Windows quirks: patch scripts go in the scratchpad, not long heredocs; Write may leave CRLF, so multi-line string patches can miss (use Edit); `gh` needs `export PATH="$PATH:/c/Program Files/GitHub CLI"`.
