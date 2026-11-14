# Contract fixtures

Canonical example responses for every endpoint in `../API_CONTRACT.md` (v1.1). The frontend's mock
mode serves these files; the backend's conformance tests (B15) validate each one against its schema.

They are one consistent snapshot of a small world, observed at **2026-11-14T18:00:00.000Z**: the same ids appear in
every file, so a link in one fixture resolves in another. Change them only through the
contract-change process in `CONTRIBUTING.md`.

## Naming

`<resource>.<operation>[.<variant>].json`. The `<resource>.<operation>` pair selects the schema
(`backend/tests/fixture_map.py`); the variant is free text. `executions.trace.<execution id>.json`
and `executions.events.<execution id>.json` exist for every execution in `executions.list.json`.

## Agents

| Slug | Health | Why |
|---|---|---|
| `invoice-processor` | failing | 9 executions, 1 open anomalies, id `agt_00000000000000000000000000000002` |
| `pr-reviewer` | idle | 0 executions, 0 open anomalies, id `agt_00000000000000000000000000000005` |
| `research-assistant` | degraded | 11 executions, 2 open anomalies, id `agt_00000000000000000000000000000001` |
| `support-triage` | healthy | 11 executions, 2 open anomalies, id `agt_00000000000000000000000000000003` |
| `ticket-digest` | degraded | 10 executions, 5 open anomalies, id `agt_00000000000000000000000000000004` |

## Scenario executions

| Key | Agent | Status | Execution id | What it is |
|---|---|---|---|---|
| `token_spike` | research-assistant | completed | `exe_00000000000000000000000000000007` | The search API returned 24 full documents instead of 3 snippets. Payloads over 64 KB are stored as `_truncated` markers; token_spike and duration_spike (both high) fire. |
| `healthy` | research-assistant | completed | `exe_00000000000000000000000000000008` | The healthy research run of the demo: plan → web_search → parse_results → summarize. |
| `schema_change` | research-assistant | failed | `exe_0000000000000000000000000000000a` | The demo failure: web_search answers {data, meta} instead of {results}; parse_results raises KeyError: 'results'. |
| `replay_different_failure` | research-assistant | failed | `exe_0000000000000000000000000000000b` | Sandbox replay of `schema_change` after a first fix that was wrong: fails with TypeError, outcome different_failure. |
| `replay_fixed` | research-assistant | completed | `exe_0000000000000000000000000000000c` | Sandbox replay of `schema_change` after the parser fix: completes, outcome fixed. |
| `new_tool` | invoice-processor | completed | `exe_00000000000000000000000000000027` | A EUR invoice made the agent call convert_currency, a tool not in its baseline: unexpected_pattern (low). |
| `ghost_invoice` | invoice-processor | completed | `exe_00000000000000000000000000000028` | The demo ghost completion: validation is down, the agent swallows it, never calls submit_invoice and reports completed. ghost_completion (critical). |
| `replay_regressed` | invoice-processor | failed | `exe_00000000000000000000000000000029` | Sandbox replay of `ghost_invoice` after making the agent raise on a validation outage: it now fails, so the outcome rule says regressed. |
| `rate_limit` | support-triage | completed | `exe_00000000000000000000000000000048` | The knowledge base answers HTTP 429 twice, then succeeds: excessive_retries (medium). Has no investigation yet; the manual-investigation fixtures are for this run. |
| `replay_both_succeeded` | support-triage | completed | `exe_0000000000000000000000000000004b` | Live replay (authorized) of `rate_limit` after the knowledge base stopped rate limiting: outcome both_succeeded, and the two failed attempts are gone. |
| `slow` | support-triage | completed | `exe_00000000000000000000000000000049` | The knowledge base takes 3.5 s to answer: duration_spike (medium). |
| `running` | support-triage | running | `exe_0000000000000000000000000000004a` | Still running at fixture time: classify is done, retrieve_kb is in flight. |
| `fetch_failed` | ticket-digest | failed | `exe_00000000000000000000000000000063` | The ticket API answers HTTP 503 on all three attempts and the run fails: repeated_tool_failure (high) and excessive_retries (medium), both resolved. Its investigation itself failed. |
| `timed_out_1` | ticket-digest | timed_out | `exe_00000000000000000000000000000065` | fetch_tickets never answers; the sweeper marks the run timed_out: stale_execution (high, acknowledged). |
| `timed_out_2` | ticket-digest | timed_out | `exe_00000000000000000000000000000066` | Second hang in a row: stale_execution (high). |
| `timed_out` | ticket-digest | timed_out | `exe_00000000000000000000000000000068` | Third hang within the agent's last 10 runs: stale_execution and repeated_timeouts (both high). |
| `replay_same_failure` | ticket-digest | failed | `exe_00000000000000000000000000000069` | Sandbox replay of `fetch_failed`: the recorded 503s fail it the same way, outcome same_failure. |
| `replay_inconclusive` | ticket-digest | completed | `exe_0000000000000000000000000000006a` | Sandbox replay of `timed_out`: it completes, but the original timed out, so the outcome is inconclusive. |

Routine healthy runs that form the baselines:

- research-assistant: 6 runs, `exe_00000000000000000000000000000001` … `exe_00000000000000000000000000000006`
- invoice-processor: 6 runs, `exe_00000000000000000000000000000021` … `exe_00000000000000000000000000000026`
- support-triage: 7 runs, `exe_00000000000000000000000000000041` … `exe_00000000000000000000000000000047`
- ticket-digest: 4 runs, `exe_00000000000000000000000000000061` … `exe_00000000000000000000000000000067`

## Investigations

| File | Execution | What it shows |
|---|---|---|
| `investigations.get.confirmed.json` | `schema_change` | Root cause confirmed by signature `missing_key_in_upstream_output` |
| `investigations.get.ghost_completion.json` | `ghost_invoice` | Confirmed by signature `ghost_completion`, trigger `auto_anomaly` |
| `investigations.get.timeout.json` | `timed_out` | Confirmed by signature `timeout_in_step`; has an evidence gap (too few baseline runs) |
| `investigations.get.probable.json` | `token_spike` | Provider `fable`: two LLM hypotheses, one with a contradicting fact; root cause `probable` |
| `investigations.get.insufficient_evidence.json` | `replay_different_failure` | No signature matched and no hypothesis: `insufficient_evidence` |
| `investigations.get.failed.json` | `fetch_failed` | The investigation itself failed |
| `investigations.create.json`, `.get.queued`, `.get.running`, `.get.manual_result` | `rate_limit` | One manual investigation in the states a client polls through. Not in `investigations.list.json`: in this snapshot nobody has started it |

## Replays

One per outcome (`replays.get.<outcome>.json`), plus `pending`, `claimed` and `failed`.
`replays.get.fixed.json` is the demo: the sandbox replay of `schema_change` after the parser fix.
`replays.get.both_succeeded.json` is the only `live` replay and is authorized.

## Things that are deliberately here

- `_truncated` payload markers: step inputs and outputs and the execution output of `token_spike`.
- Nested steps (`depth` 1): `summarize_batch` under `summarize` in the `ticket-digest` runs.
- A retried step: `retrieve_kb` attempts 1–3 in `rate_limit`; `fetch_tickets` in `fetch_failed`.
- `cost_usd` is `null` for `demo-llm-1` (no pricing) and set for the `ticket-digest` runs, using a
  fixture-only price for `claude-haiku-5-5`. The backend's pricing table (B14) is not built yet.
- Evidence of kind `event` (on the `ghost_completion` anomaly) and `metric` (on the `slow` run's
  `duration_spike`). The backend's v1 rules do not emit these two kinds; they are here so every
  `EvidenceKind` has an example.
- Anomaly statuses `acknowledged` and `resolved`, although `PATCH /anomalies/{id}` is P1.
- An empty page for each list endpoint and one file per error code.

## Regenerating

Authored by `frontend/scripts/build-fixtures.ts` from `frontend/scripts/fixtures/story.ts`; titles,
explanations, facts and signatures follow the backend's rule and report templates. Check with
`cd frontend && npm run validate-fixtures`.
