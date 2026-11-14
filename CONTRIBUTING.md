# Contributing to Ghostwatch

## Branches

| Branch | Purpose | Who pushes |
|---|---|---|
| `main` | Stable, integrated, demo-ready. Protected: PR + 1 approval required. | Nobody directly |
| `jayden/backend` | Jayden's integration branch | Jayden |
| `adit/frontend` | Adit's integration branch | Adit |
| `feature/<owner>-<topic>` | Optional short-lived branches cut from your integration branch | Owner |
| `contract/<topic>` | Contract changes only | Either, approved by both |

Flow: `feature/*` → your integration branch → PR to `main` at sync points (T+12, T+29) and whenever a feature is complete and tested.

## Pull requests
- One feature per PR, ideally under ~500 changed lines.
- Title: `[B5] Event ingestion and step derivation` (issue id in brackets).
- Description: what changed, how it was tested (commands and output), contract impact (`none` or a link to the contract PR), screenshots for UI.
- The other developer reviews. Target turnaround: 30 minutes during work windows.
- The PR is green in CI before merge. Use squash merges.

## Commits
Conventional Commits: `feat(scope): ...`, `fix(scope): ...`, `test(scope): ...`, `docs: ...`, `chore: ...`. Reference issues with `Refs #N`.

## Labels
`backend`, `frontend`, `integration`, `bug`, `documentation`, `contract-change`, `priority: high`, `P0`, `P1`, `P2`.

## Contract change process
The contract (`contract/`) is frozen. To change it:
1. The developer who needs the change opens a `contract/<topic>` branch touching **only** `contract/`: `API_CONTRACT.md`, updated fixtures and a changelog row.
2. Label it `contract-change`; both developers must approve.
3. After merge: the backend implements it, the frontend updates `lib/api/types.ts` and re-syncs fixtures. Both note it in their PROGRESS.md.
4. Additive changes (a new optional field or endpoint) can be fast-tracked by agreeing on chat. Breaking changes (rename, remove, type change) need a short call.

**Contract Change Request format** (what a Claude writes for its human to forward):
```
CONTRACT CHANGE REQUEST
Requested by: <Jayden|Adit>'s side
Section: <e.g. §6 Traces>
Change: <exact field/endpoint/enum change>
Type: additive | breaking
Why: <the concrete problem this solves>
Impact on other side: <what they must change, or "none">
Proposed fixture diff: <snippet>
```

## Secrets
Never commit `.env*` (except `.env.example`), API keys, tokens or database dumps. If a secret is committed, rotate it immediately; removing it from git is not enough.

## Definition of "done" for any task
Acceptance criteria met · tests written and passing · no contract drift · PROGRESS.md updated · PR opened with test evidence.
