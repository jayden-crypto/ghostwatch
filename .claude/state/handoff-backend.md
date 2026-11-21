# Handoff — Jayden's backend session (committed, backend side only; durable status is in backend/PROGRESS.md)
## Decisions
- Contract v1.2 sandbox rule; `@gw.tool` without `side_effects` means True. No paid API calls: LLM_PROVIDER=rule_based everywhere; nothing may claim the demo used Fable. Adit confirmed v1.1 and v1.2 as on main (2026-11-18 UTC).
- Repo writes need gh's active account to be jayden-crypto; if not, tell Jayden, don't switch it. Every text read/write names UTF-8 (`PYTHONWARNDEFAULTENCODING=1 uv run pytest -q`).
- Scratch rehearsal: database `ghostwatch_demo`, uvicorn on 8001, GHOSTWATCH_API_URL and the frontend's NEXT_PUBLIC_API_BASE_URL pointed at it; drop it afterwards. Never write in frontend/ (Adit's): build/run it in a temp worktree of origin/main, env vars inline.
- Handoff per side (#41, merged 8d71898). This file is committed and the repo is public: no secrets or personal details. Never write handoff-frontend.md.
## Done / settled
- PRs #35–#41 merged to main (#40 = demo script, 4ac9ad6, approved by Adit); main merged into jayden/backend (fd50983), 617 tests pass.
- Dev DB on 8000: 3 agents, 77 runs, 2 anomalies; the 7-day window drops older seeded runs, so reseed on demo day (script setup says so). Keep it clean.
- One stall reproduced (2026-11-18 UTC): React reveals streamed Suspense content on requestAnimationFrame; an off-screen pane draws no frames, so the trace page never fetches until shown (dev and prod, after #39). The 11-17 "request already 200" case stays unexplained.
- Prod build of main (fe86776) checked live on scratch 8001, partially; the not-checked list is in DEMO_SCRIPT.md's rehearsal log.
## Declined / not done
- BOM tolerance in `.env`: not done. PROJECT_PLAN §11 step 3 not edited; the script follows what happens.
- Did not comment on or close #28; no tunnel or public URL for the backend offered to Adit.
## Next step
- #34 stays open until three human rehearsals and the backup recording. Adit's #40 note: setup step 4 could use a production build (`npm run build && npm run start`); open, not decided (steps 1–7 never rehearsed on a prod build). Adit is looking into the step 5 stall on his side.
