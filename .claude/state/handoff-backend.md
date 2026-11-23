# Handoff — Jayden's backend session (committed, backend side only; durable status is in backend/PROGRESS.md)
## Decisions
- Contract v1.2 sandbox rule; `@gw.tool` without `side_effects` means True. No paid API calls: LLM_PROVIDER=rule_based everywhere; nothing may claim the demo used Fable. Adit confirmed v1.1 and v1.2 as on main (2026-11-18 UTC).
- Repo writes need gh's active account to be jayden-crypto; if not, tell Jayden, don't switch it. Every text read/write names UTF-8 (`PYTHONWARNDEFAULTENCODING=1 uv run pytest -q`).
- Scratch rehearsal: database `ghostwatch_demo`, uvicorn on 8001, GHOSTWATCH_API_URL and the frontend's NEXT_PUBLIC_API_BASE_URL pointed at it; drop it afterwards. Never write in frontend/ (Adit's): build/run it in a temp worktree of origin/main, env vars inline.
- Handoff per side (#41, merged 8d71898). This file is committed and the repo is public: no secrets or personal details. Never write handoff-frontend.md.
## Done / settled
- PRs #35–#51 merged to main (#48 F12 results 64bef25; #49 the rest of F12 94d1be1; #51 e90c5d8) (#40 demo script 4ac9ad6; #42 prod-build rehearsal c14d853; #43 id pages without frames 847ad44 and #44 its review notes 986eee6, both approved by Jayden); #45 (step 4 docs) approved by Adit, merged 3a170d2; main merged into jayden/backend after it. #47 (Adit's #45 note: step 4 is Jayden and Adit's decision) approved by Adit, merged f7878d3.
- Dev DB on 8000: 3 agents, 77 runs, 2 anomalies; the 7-day window drops older seeded runs, so reseed on demo day (script setup says so). Keep it clean.
- One stall reproduced (2026-11-18 UTC): React reveals streamed Suspense content on requestAnimationFrame; an off-screen pane draws no frames, so the trace page never fetched until shown (dev and prod, after #39). Fixed by #43.
- Prod build of main (fe86776) checked live on scratch 8001, partially; the not-checked list is in DEMO_SCRIPT.md's rehearsal log.
## Declined / not done
- BOM tolerance in `.env`: not done. PROJECT_PLAN §11 step 3 not edited; the script follows what happens.
- #34 left open on purpose; no tunnel or public URL for the backend offered to Adit.
## Next step
- 2026-11-22 (UTC) Jayden and Adit's decisions: setup step 4 is a production build (DEMO_SCRIPT.md here; /settings wording, README Dashboard section and the CLAUDE.md handoff line in Adit's #46, merged a0ba982); issues #19–#27, #29–#33 closed with evidence comments; F12 (#28): every item Adit's side listed checked live on 2026-11-23 (prod build of 3a170d2, scratch 8001) plus one authorized live replay (invoice run, submit_invoice executed against the fake service); results in DEMO_SCRIPT.md after the 2026-11-18 list. Results posted on #28 (Jayden's yes). #28 closed by Adit on 2026-11-23 after #49 (every criterion shown live). Not seen: Retry recovering a page, an investigation shown as running. Adit's #49 note fixed in #51 (e90c5d8).
- #34 (2026-11-24): Adit's comment there proposes waiving the Docker steps of his clean-clone test, three human runs on Jayden's Mac (Claude runs don't count), recording one, one offline, and one §10 comment agreed by both; Jayden's agreement not yet recorded in #34. Adit's #52 (pause list polling on a 4xx) approved by Jayden at 932519f. The detail-page stall is fixed by #43; the 11-17 "request already 200" case stays unexplained.
