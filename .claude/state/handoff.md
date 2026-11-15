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
- Local, unpushed: 14e4650 (B12 replay API), the .claude hooks commits and the B13 commit ("feat(sdk): sandbox replay and replay worker"). Push only with a regenerated docs/API.md (`uv run python -m scripts.api_docs` on a seeded server; the script needs replay sections first); the docs-coverage test fails until then.
- B13 was shown to Jayden live: schema-change → `replay.py worker --fixed` → `replay.py request <id>` gave outcome `fixed`. Verify Jayden accepted it before treating B13 as closed.
- Adit's fixtures PR #35: all 145 fixtures passed B15 in a scratch worktree; the PR itself is not reviewed on GitHub yet.
## Next step
- B14 (token cost from a pricing table; `cost_usd` null unless every model is priced), then PATCH /anomalies/{id}, regenerate docs, push.
