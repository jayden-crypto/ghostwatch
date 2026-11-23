# Handoff — Jayden's backend session (committed, backend side only; durable status is in backend/PROGRESS.md)
## Decisions
- Contract v1.2 sandbox rule; `@gw.tool` without `side_effects` means True. No paid API calls: LLM_PROVIDER=rule_based everywhere; nothing may claim the demo used Fable. Adit confirmed v1.1 and v1.2 as on main (2026-11-18 UTC).
- Repo writes need gh's active account to be jayden-crypto; if not, tell Jayden, don't switch it. Every text read/write names UTF-8 (`PYTHONWARNDEFAULTENCODING=1 uv run pytest -q`).
- Scratch rehearsal: database `ghostwatch_demo`, uvicorn on 8001, GHOSTWATCH_API_URL and the frontend's NEXT_PUBLIC_API_BASE_URL pointed at it; drop it afterwards. Never write in frontend/ (Adit's): build/run it in a temp worktree of origin/main, env vars inline.
- Handoff per side (#41, merged 8d71898). This file is committed and the repo is public: no secrets or personal details. Never write handoff-frontend.md.
## Done / settled
- PRs #35–#44 merged to main (#40 demo script 4ac9ad6; #42 prod-build rehearsal c14d853; #43 id pages without frames 847ad44 and #44 its review notes 986eee6, both approved by Jayden); main merged into jayden/backend (66627a4).
- Dev DB on 8000: 3 agents, 77 runs, 2 anomalies; the 7-day window drops older seeded runs, so reseed on demo day (script setup says so). Keep it clean.
- One stall reproduced (2026-11-18 UTC): React reveals streamed Suspense content on requestAnimationFrame; an off-screen pane draws no frames, so the trace page never fetched until shown (dev and prod, after #39). Fixed by #43.
- Prod build of main (fe86776) checked live on scratch 8001, partially; the not-checked list is in DEMO_SCRIPT.md's rehearsal log.
## Declined / not done
- BOM tolerance in `.env`: not done. PROJECT_PLAN §11 step 3 not edited; the script follows what happens.
- #28 and #34 left open on purpose; no tunnel or public URL for the backend offered to Adit.
## Next step
- 2026-11-22 (UTC) Jayden's decisions: setup step 4 is a production build (done in DEMO_SCRIPT.md; Adit's side changes /settings wording); Adit's side writes the README dashboard section and the CLAUDE.md "no secrets/personal details in handoffs" line, in PRs Jayden reviews; issues #19–#27, #29–#33 closed with evidence comments; #28 waits for Adit to pick which F12 live checks remain, then this session runs them on a scratch backend.
- #34 stays open until three human rehearsals and the backup recording. The detail-page stall is fixed by #43; the 11-17 "request already 200" case stays unexplained.
