# Handoff (Jayden's backend session; written by hand)
## Decisions
- Sandbox replay rule is contract v1.2 (on main, 4b7568d): recorded calls are served; an unrecorded call runs only if it is an LLM call or a tool with side_effects=False; anything else is blocked (SandboxRecordingMissing). Why: under v1.1 a fixed agent could never reach `fixed`, because summarize has no recording.
- `@gw.tool` without `side_effects` defaults to True: unknown means unsafe. Every replay step carries `metadata.replay_source` (recorded|executed|blocked), and StepDiff mirrors it, so `fixed` is checkable.
- Adit's Replay dialog copy ("nothing external runs") is wrong; the corrected wording is in the 4b7568d commit message.
## Declined / waiting on Jayden
- Do not open the jayden/backend → main PR until Jayden asks.
- Contract v1.1 and v1.2 went to main on Jayden's instruction; Adit has to confirm both.
- Open question: make the handoff per-developer (handoff.jayden.md / handoff.adit.md) before .claude/ and CLAUDE.md reach main, since Adit's session would write the same file. Recommended; not done.
## Half-finished (verify before continuing)
- Local, unpushed: 14e4650 (B12 replay API) and the .claude hooks commits. Push only with a regenerated docs/API.md (`uv run python -m scripts.api_docs` on a seeded server); the docs-coverage test fails until then.
- B13 is uncommitted in sdk/python (replay.py, worker.py, tools.py, execution.py, tests). SDK tests were not rerun after the last edits. Still to do: SDK replay tests; mark read-only demo tools (web_search, retrieve_kb) side_effects=False; demo worker and parser-fix switch.
- Adit's fixtures PR #35: all 145 fixtures passed B15 in a scratch worktree; the PR itself is not reviewed on GitHub yet.
## Next step
- Finish B13, then run schema-change → parser fix → sandbox replay and show Jayden outcome `fixed` (web_search recorded, summarize executed) before calling it done. Then B14, PATCH /anomalies/{id}, regenerate docs, push.
