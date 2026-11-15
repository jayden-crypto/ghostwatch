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
- Local, unpushed: 14e4650 (B12 replay API), the .claude hooks commits, d4350c0 (B13), 9fa472e (B14) and the commit "feat(anomalies): PATCH status, and docs for replay, cost and PATCH". docs/API.md is regenerated and all suites pass, so the branch can be pushed once Jayden says so.
- B13 was shown to Jayden live (outcome `fixed`) and he said to go on to B14.
- B14 prices come from the published Anthropic pricing page read on 2026-11-15; cost is null unless every step that reported tokens can be priced.
- Adit's fixtures PR #35: all 145 fixtures passed B15 in a scratch worktree; the PR itself is not reviewed on GitHub yet.
## Next step
- Backend P0 and P1 are complete. Ask Jayden: push jayden/backend? open the PR to main? Then review Adit's fixtures PR #35.
