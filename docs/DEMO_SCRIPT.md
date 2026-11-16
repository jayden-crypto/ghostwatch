# Ghostwatch demo script

> Your agents say they're working. Ghostwatch makes sure they actually are.

**Status: draft.** The terminal half was rehearsed twice from an empty database on 2026-11-16 and every output quoted below is from those runs. The dashboard half has not been run against the live backend yet (issue #28, F12): each dashboard step is marked **[dashboard: not verified live]** and describes what the frontend does in mock mode, taken from `frontend/PROGRESS.md` on `adit/frontend`. Remove a mark only after doing that step for real.

The demo needs no network and no API key. The three agents call small fake services, and investigations run on `LLM_PROVIDER=rule_based`, which is deterministic code. No model is called at any point.

## What the audience should take away

1. Every step an agent takes is recorded, and the trace is built from those records.
2. Ghostwatch catches a run that reports success without doing its job.
3. A root cause is marked confirmed only when recorded evidence proves it.
4. A failed run can be replayed safely against its recording to prove a fix.

## Setup, before anyone is watching

Three terminals and one browser window.

| Where | For |
|---|---|
| Terminal 1 | the backend |
| Terminal 2 | demo commands |
| Terminal 3 | the replay worker (started in step 6, not before) |
| Browser | the dashboard at `http://localhost:3000` |

**1. Start from empty data.** This deletes everything Ghostwatch has stored on this machine. Skip it on a fresh clone.

```bash
docker compose down -v
```

**2. Start Postgres and the backend** (terminal 1).

```bash
cp .env.example .env
```
```bash
docker compose up -d
```
```bash
cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app
```

**3. Seed a week of history** (terminal 2). It takes about two seconds.

```bash
cd demo && uv run python seed.py
```

Expected output:

```
Sent 77 executions.

agent                 health      runs  success  open anomalies
invoice-processor     healthy       25     100%               0
research-assistant    healthy       25     100%               0
support-triage        degraded      27     100%               2
  [medium] excessive_retries on Support Triage: 2 retried steps, highest attempt 3
  [high] duration_spike on Support Triage: Duration 6.1× above baseline
```

The duration-spike figure varies slightly between runs (6.1× and 6.2× were both seen).

Use plain `seed.py`, not `seed.py --all`. `--all` also seeds the two failures, which this script produces live.

**4. Start the dashboard in live mode.** **[dashboard: not verified live]** Until `adit/frontend` is merged, `frontend/` exists only on that branch. Create `frontend/.env.local` with:

```
NEXT_PUBLIC_API_MODE=live
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

```bash
cd frontend && npm i && npm run dev
```

Open `/settings` and check that the data source says live and the investigation provider says `rule_based`. If it says mock, the numbers on screen are fixtures, not this backend: stop and fix `.env.local` before presenting.

## The demo

Each step has what to do, what to say, and what must be on screen before moving on. Every command runs in terminal 2 from `demo/` and takes about one second.

### 1. Overview: three agents, real history, one degraded

**Do.** Open the dashboard's Overview (`/`). **[dashboard: not verified live]**

**Say.** "Three agents have been running for a week. Every number here was computed by the backend from events the agents sent through our SDK. Nothing was inserted into the database. Two agents are healthy; Support Triage is degraded."

**Expect.** 3 agents, 77 executions, 0 failed, 100% success, 2 open anomalies. Support Triage is degraded with two anomalies: excessive retries (medium) and a duration spike (high).

### 2. A healthy run and its trace

**Do.**

```bash
uv run python run_scenario.py healthy research-assistant
```

```
Ghostwatch   : execution exe_…
  status     : completed in 880 ms, 4 steps
   1. plan: completed, 0 ms
   2. web_search: completed, 391 ms
   3. parse_results: completed, 0 ms
   4. summarize: completed, 490 ms
  anomalies  : none
  investigation: none

Open in the dashboard: http://localhost:3000/executions/exe_…
```

Open the printed link. **[dashboard: not verified live]** Walk the waterfall: four steps in order, each with its duration, input and output.

**Say.** "The agent planned, searched, parsed the results and summarised. This is the same data the terminal just printed, read back from the API."

**Expect.** Four completed steps. Durations vary by a few milliseconds between runs.

### 3. The search API changes its response, and the agent fails

**Do.**

```bash
uv run python run_scenario.py schema-change
```

```
Scenario     : schema-change - The search API now answers {"data": ..., "meta": ...} instead of {"results": ...}.
Agent result : raised KeyError: 'results'

Ghostwatch   : execution exe_…
  status     : failed in 394 ms, 3 steps
   1. plan: completed, 0 ms
   2. web_search: completed, 390 ms
   3. parse_results: failed, 2 ms  <- KeyError: 'results'
  anomalies  : none
  investigation: confirmed (signature missing_key_in_upstream_output), provider rule_based
               Step 3 parse_results read the key 'results', which the output of Step 2 web_search (tool web_search) does not contain. That output's keys are: data, meta.
```

**Copy the execution id.** Step 6 needs it.

**Say.** "An upstream service changed its response. The agent crashed with a `KeyError`, which on its own tells you very little. Ghostwatch started an investigation by itself the moment the run failed."

**Expect.** Status failed, three steps, an investigation that is already `confirmed`. A single failed run raises no anomaly, so `anomalies: none` is correct here and the agent's health stays healthy; do not say an anomaly appeared.

### 4. The investigation: a confirmed root cause, with evidence

**Do.** Open the printed link and the Investigation tab of the trace page. **[dashboard: not verified live]** Point at the confirmed banner and its signature, then at the facts, then click the evidence of F5 and of F3 to jump to the steps.

**Say.** "Confirmed is a strong word, and only deterministic code is allowed to use it. The signature matched two recorded facts: step 3 read the key `results`, and the output of step 2 has the keys `data` and `meta` and no `results`. Every fact links to the record it came from. A language model can add hypotheses in another configuration, but it can never mark one confirmed."

**Expect.** These facts, with these ids:

| Fact | Statement |
|---|---|
| F3 | Step 3 `parse_results` failed with `KeyError: 'results'` (evidence: the step's error message and stack trace) |
| F5 | Step 2 `web_search` returned an object with keys `data`, `meta` (evidence: the step's output) |

The report has seven facts (F1–F7) and one hypothesis, H1, which is the confirmed root cause. The provider shown is `rule_based`.

### 5. The ghost: the agent says it worked, and it did not

**Do.**

```bash
uv run python run_scenario.py ghost-invoice
```

```
Scenario     : ghost-invoice - The validation service is down; the agent swallows the error and still reports success.
Agent result : returned {'status': 'processed', 'invoice_number': 'INV-2042'}

Ghostwatch   : execution exe_…
  status     : completed in 226 ms, 2 steps
   1. extract_fields: completed, 0 ms
   2. validate: completed, 226 ms
  anomaly    : [critical] ghost_completion: Reported completed, but submit_invoice never completed
  investigation: confirmed (signature ghost_completion), provider rule_based
```

Open the Anomalies page (`/anomalies`). **[dashboard: not verified live]**

**Say.** "Look at what the agent returned: status processed. No exception, no error log. A monitor that trusts the agent's own status shows green. But the invoice was never submitted. Ghostwatch knows the run was supposed to complete a `submit_invoice` step, and no such step exists in the record. That is what the tagline means."

**Expect.** Execution status `completed`, one critical `ghost_completion` anomaly, Invoice Processor's health changes to failing, open anomalies go from 2 to 3.

### 6. Fix the parser and prove it with a sandbox replay

**Do.** Show `parse_results` in `demo/agents/research_assistant.py`: the fix reads the hits from `data` when `results` is missing. The `--fixed` flag below deploys that fix to the worker; without the flag the worker runs the agent as it shipped.

Start the worker in terminal 3:

```bash
cd demo && uv run python replay.py worker --fixed
```

Then request a sandbox replay of the failed run from step 3. On the dashboard: the Replay button on that run's trace page, with Sandbox selected. **[dashboard: not verified live]** From the terminal, which does the same thing:

```bash
uv run python replay.py request <execution_id>
```

```
  status     : completed
  outcome    : fixed
  original   : failed in 394 ms, 3 steps  <- KeyError: 'results'
  replay     : completed in 501 ms, 4 steps
  steps      :
    1. plan           unchanged       completed -> completed  executed (ran for real in this replay)
    2. web_search     unchanged       completed -> completed  recorded (served from the original run, not called)
    3. parse_results  status_changed  failed -> completed     executed (ran for real in this replay)
    4. summarize      added           - -> completed          executed (ran for real in this replay)
```

**Say.** "The server never runs agent code. A worker that has the agent's code picked the replay up. The search was not called again: the replay was given the exact response that broke production. The parser ran for real, and this time it passed. Outcome: fixed. In a sandbox replay a tool with side effects never runs."

**Expect.** Outcome `fixed`. `web_search` is `recorded`; `parse_results` changes from failed to completed; `summarize` is added.

Optional, if there is time: run the worker without `--fixed` first. The same request gives `same_failure`, which shows the replay reproduces the bug before it proves the fix. Each failing replay is itself a failed execution of the agent, so the failure count on the overview goes up by one.

### 7. A live replay needs explicit authorization

**Do.** Open the Replay dialog again and choose Live. **[dashboard: not verified live]** The submit button stays disabled until the box "I authorize real external side effects for this replay" is ticked. Do not tick it. To show the server enforces the same rule:

```bash
curl -s -X POST localhost:8000/api/v1/executions/<execution_id>/replay -H 'content-type: application/json' -d '{"mode":"live"}'
```

```
{"error":{"code":"side_effect_authorization_required","message":"A live replay runs the agent's tools for real. Set authorize_side_effects to true to confirm, or use mode sandbox.","details":null}}
```

**Say.** "A live replay would run every tool for real, including the ones that send money. The API refuses it unless the request says so explicitly."

**Expect.** HTTP 422 with code `side_effect_authorization_required`.

## If something goes wrong

| What you see | Cause | What to do |
|---|---|---|
| A demo command prints `Cannot reach Ghostwatch at …` | The backend is not running | Restart it in terminal 1 |
| `status : still pending. Is a worker running?` | No replay worker | Start it in terminal 3. A pending replay is picked up as soon as a worker starts; no need to request again |
| The dashboard shows numbers that do not match the terminal | It is in mock mode | Check `/settings`; fix `frontend/.env.local` and restart `npm run dev` |
| The dashboard is unusable | | Carry on from the terminal. Every step above prints the same facts the dashboard shows, read from the same API |
| A step was run twice or out of order | | The story still holds, but the counts in "Expect" will be off. For a clean run, repeat the setup |

## What this demo does not show

- No language model is called. Investigations use the rule-based provider. The optional Fable provider has never been run against the real API.
- The agents' services are fakes inside `demo/`, so the failures are controlled and repeatable.
- Tokens and cost are empty for these runs: the demo's fake model reports no token usage, and Ghostwatch shows unknown as unknown.
- A live replay is never performed.

## Rehearsal log

The definition of done asks for three end-to-end runs without intervention. Add a row for every rehearsal.

| Date | Who | What was run | Result |
|---|---|---|---|
| 2026-11-16 | Jayden's Claude session | Terminal half, from an empty database, on macOS: seed, steps 2, 3, 5, 6 (with and without `--fixed`), 7 | Every output matched this script |
| 2026-11-16 | Jayden's Claude session | Terminal half again from an empty database, in script order, with agent health and overview checked after every step | Every output matched this script |
| | | Full run with the dashboard in live mode | Not done yet |

Not done in those rehearsals: `docker compose down -v` (they used a separate empty database instead, so that existing data was kept), and anything in a browser.
