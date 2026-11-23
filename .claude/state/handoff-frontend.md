# Handoff — Adit's frontend session (committed, frontend side only; durable status is in frontend/PROGRESS.md)

- `main` has the whole frontend: PR 38 (F1–F11, F13, b36be58), PR 39 (query results by microtask, fe86776) PR 43 (id pages read their id in the browser, 847ad44) and PR 44 (review notes on 43, live checks per page, 986eee6). `adit/frontend` is `main` merged back after 986eee6. Read `frontend/PROGRESS.md` first.
- Left in F12 (#28): Jayden's session checked lists, filters across reloads and ack/resolve/reopen on a production build (`docs/DEMO_SCRIPT.md`, PR 40 merged as 4ac9ad6); its "Not checked" list is what remains. No Docker here.
- Fixed in PR 43: [id] pages stayed empty in a pane that draws no frames (React reveals server-streamed content on requestAnimationFrame); they now read the id with `useParams()`, guarded by `e2e/no-frames.spec.ts`. Jayden confirmed it hidden on macOS. The 2026-11-17 "request already 200" case is still unexplained.
- 2026-11-18 (UTC): Adit confirmed contract v1.1 and v1.2 to Jayden in writing (frontend files aligned to Jayden's date on 2026-11-22).
- Decided 2026-11-22 (UTC) by Adit and Jayden: demo setup step 4 is a production build; this side wrote the `/settings` rebuild wording, the README Dashboard section and the CLAUDE.md "no secrets or personal details" line (one PR, Jayden reviews). Jayden closed the merged issues; #28 and #34 stay open. F12: Adit picks the checks, Jayden's session runs them.
- Never merge to `main`, force-push, open PRs or post reviews without Adit's OK.
- Decisions: settings is read-only (config is build-time); components never read `API_MODE` (the /settings route passes it as props); replay wording lives in `frontend/lib/replay.ts` (contract v1.2 text).
- Handoff per side: PR 41 merged (8d71898). Never write `handoff-backend.md` from here. The repo is public: no secrets or personal details in either handoff.
- In e2e tests click the visible card or label, never force-click an sr-only input (fails on Linux Chromium).
- Not verified: the hooks running through Claude Code's own hook runner on Windows; only the settings.json commands were run under Git Bash. Jayden ran save-state.sh on macOS: works.
- Windows quirks: patch scripts go in the scratchpad, not long heredocs; Write may leave CRLF, so multi-line string patches can miss (use Edit); `gh` needs `export PATH="$PATH:/c/Program Files/GitHub CLI"`.
