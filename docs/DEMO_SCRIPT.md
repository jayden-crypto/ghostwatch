# Ghostwatch demo script

> Your agents say they're working. Ghostwatch makes sure they actually are.

**Status: draft.** The terminal half was rehearsed twice from an empty database on 2026-11-16, and the whole script, dashboard included, on 2026-11-17 (dev server) and 2026-11-21 (production build), with the frontend in live mode. The terminal outputs quoted below are from those runs; what was and was not checked on the dashboard is in the rehearsal log at the end. The definition of done asks for three full runs.

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

Seed on the day of the demo (UTC): the history goes back 6 days, and step 1's numbers count only the 7-day window, so older seeds show fewer runs. Use plain `seed.py`, not `seed.py --all`. `--all` also seeds the two failures, which this script produces live.

**4. Start the dashboard in live mode.** Create `frontend/.env.local` with:

```
NEXT_PUBLIC_API_MODE=live
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

```bash
cd frontend && npm ci && npm run build && npm run start
```

This is a production build, the setup rehearsed on 2026-11-21. Both values are built into the app: after changing `.env.local`, run `npm run build` again before `npm run start`; restarting alone keeps the old values. (`npm run dev` also works and reads `.env.local` on start, but was last rehearsed on 2026-11-17.)

Open it at `http://localhost:3000`, not `127.0.0.1`: the backend's CORS setting allows only that origin.

Open `/settings` and check that Mode says Live, the API base URL is `http://localhost:8000/api/v1`, and Hypotheses by says Rule-based. If it says mock, the numbers on screen are fixtures, not this backend: stop, fix `.env.local` and rebuild before presenting.

**5. Open every page once, in the window you will present from.** In the 2026-11-17 run, pages sometimes sat on a loading skeleton for 5–20 seconds; once, the trace page's API request had already answered. On 2026-11-18 one cause of a stall was found and reproduced, in a browser pane that was not on screen:
- The trace page streams its content in, and React shows streamed content on the next animation frame. A pane that is not drawn produces no frames.
- So the content stayed hidden and the page's API request did not even start until the pane was shown: at least 20 s on a production build, about 104 s on the dev server. The page reported itself `visible` throughout. This was seen on trace pages only, and still happened after PR #39.
- **Fixed by PR #43** (847ad44): the trace, replay, agent and investigation pages now read their id in the browser, so nothing waits for a frame. Checked on 2026-11-22 on a production build against a real backend: with the pane hidden and no frame drawn, all four requested their data within 61–136 ms of load and showed their content.
- The 2026-11-17 case where the request had already answered is a different symptom, and remains unexplained.
- With the pane shown, Overview, a trace page, a replay and an investigation had their content 0.2–0.8 s after load on a production build, 20–70 ms after their API response.

So present from a window that is on screen, with the tab in front. Before anyone is watching, open Overview, Agents, Anomalies, Investigations, Replays and an execution's trace page there. If they are slow even so, tell Adit, and keep the terminal steps as the fallback.

## The demo

Each step has what to do, what to say, and what must be on screen before moving on. Every command runs in terminal 2 from `demo/` and takes about one second.

### 1. Overview: three agents, real history, one degraded

**Do.** Open the dashboard's Overview (`/`).

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

Open the printed link. Walk the waterfall: four steps in order, each with its duration, input and output.

**Say.** "The agent planned, searched, parsed the results and summarised. This is the same data the terminal just printed, read back from the API."

**Expect.** Four completed steps. Durations vary by a few milliseconds between runs. The header shows about 199 tokens and a cost of "—": the fake model reports token usage, but `demo-llm-1` has no price, so the cost is unknown.

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

**Do.** Open the printed link and the Investigation tab of the trace page. Point at the confirmed root cause and its signature, then at the facts, then click "Open step" under the evidence of F5 and of F3: each selects that step in the waterfall.

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
               The execution reported status completed, but expected 1 step never completed: submit_invoice. Rule fires when a completed execution has a step still running, an expected step (config.expected_steps) with no completed step, or no steps at all.
  investigation: confirmed (signature ghost_completion), provider rule_based
               The agent reported the run as completed, but the recorded steps contradict it: Reported completed, but submit_invoice never completed.
```

Open the Anomalies page (`/anomalies`). The critical anomaly is at the top; its evidence shows the observed steps `extract_fields, validate` against the expected `extract_fields, validate, submit_invoice`.

**Say.** "Look at what the agent returned: status processed. No exception, no error log. A monitor that trusts the agent's own status shows green. But the invoice was never submitted. Ghostwatch knows the run was supposed to complete a `submit_invoice` step, and no such step exists in the record. That is what the tagline means."

**Expect.** Execution status `completed`, one critical `ghost_completion` anomaly, Invoice Processor's health changes to failing, open anomalies go from 2 to 3.

### 6. Fix the parser and prove it with a sandbox replay

**Do.** Show `parse_results` in `demo/agents/research_assistant.py`: the fix reads the hits from `data` when `results` is missing. The `--fixed` flag below deploys that fix to the worker; without the flag the worker runs the agent as it shipped.

Start the worker in terminal 3:

```bash
cd demo && uv run python replay.py worker --fixed
```

Then request a sandbox replay of the failed run from step 3. On the dashboard: the Replay button on that run's trace page, Sandbox (selected by default), then "Request sandbox replay". The dashboard opens the replay and shows the comparison once the worker has run it, within a few seconds: outcome Fixed, "1 served from the recording, 3 really ran, 0 blocked", and the same step table as below. From the terminal, which does the same thing:

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

**Do.** Open the Replay dialog again and choose Live. The "Request live replay" button stays disabled until the box "I authorize real external side effects for this replay" is ticked. Do not tick it; close the dialog with Cancel. To show the server enforces the same rule:

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
| The dashboard shows numbers that do not match the terminal | It is in mock mode | Check `/settings`; fix `frontend/.env.local`, then `npm run build` and `npm run start` again |
| The dashboard is unusable | | Carry on from the terminal. Every step above prints the same facts the dashboard shows, read from the same API |
| A step was run twice or out of order | | The story still holds, but the counts in "Expect" will be off. For a clean run, repeat the setup |

## What this demo does not show

- No language model is called. Investigations use the rule-based provider. The optional Fable provider has never been run against the real API.
- The agents' services are fakes inside `demo/`, so the failures are controlled and repeatable.
- Cost is unknown for these runs: the fake model reports token usage, but `demo-llm-1` is not a priced model, and Ghostwatch shows an unknown cost as "—", never as $0.
- A live replay is never performed.

## Rehearsal log

The definition of done asks for three end-to-end runs without intervention. Add a row for every rehearsal.

| Date | Who | What was run | Result |
|---|---|---|---|
| 2026-11-16 | Jayden's Claude session | Terminal half, from an empty database, on macOS: seed, steps 2, 3, 5, 6 (with and without `--fixed`), 7 | Every output matched this script |
| 2026-11-16 | Jayden's Claude session | Terminal half again from an empty database, in script order, with agent health and overview checked after every step | Every output matched this script |
| 2026-11-17 | Jayden's Claude session | Full run with the dashboard in live mode (dev server, macOS, Node 26), against a scratch backend on port 8001 with its own empty database: setup check on `/settings`, then steps 1–7 in order, step 6 from the dashboard's Replay button | Every step's terminal output and the screens checked matched, after two corrections made to this script in the same run: demo runs do report tokens (only cost is unknown), and step 5 prints two description lines. No console errors and no unexpected API errors (the only 4xx were a 404 for the healthy run's missing investigation and the deliberate 422 in step 7). Slow loading seen; see setup step 5 |
| 2026-11-21 | Jayden's Claude session | Full run on a production build of `main` at 4ac9ad6 (`npm run build && npm run start`, live mode, macOS), against a scratch backend on port 8001 with its own empty database: seed, setup check on `/settings`, the pages setup step 5 names opened once, then steps 1–7 in order, step 6 from the dashboard's Replay button | The terminal output of the seed and of steps 2, 3, 5 and 7 matched this script (step 2's block leaves out the Scenario and Agent result lines the command prints first), and every screen checked matched. Also checked this time: F3's and F5's "Open step" links, and `web_search`'s input and output in the inspector. No console errors when the console was read at the end. Jayden clicked in the pane a few times during the run. Some detail pages were slow; see below |

Not checked in the 2026-11-17 run: F3's "Open step" link (F5's was clicked), any step's input and output in the inspector, `frontend/.env.local` (the two variables were passed on the command line instead), and a production build. Whether this run counts towards the three the definition of done asks for is for Jayden and Adit to decide: it was a Claude session, not a person presenting.

About the 2026-11-21 run:
- **Timing, list pages:** Overview, Agents, Anomalies, Investigations and Replays had their content 148–300 ms after load, every time they were timed (twice for Overview and Anomalies, once for the others). On the very first Overview load a text read, not timed, found no content although every API request had answered by 176 ms; the reload showed content at 300 ms.
- **Timing, detail pages:** the trace page, its Investigation tab and the replay page were often slow, with the pane reported as displayed. From the browser's own records, their API request started 1.0, 1.1, 1.2, 3.0, 3.0, 3.9 and 7.0 s after load, and the 7.0 s load had its first paint at 7.06 s. Once the request started at 0.34 s, but the content was only found at 4.7 s. Twice the trace page was fast (184 and 406 ms). When content appeared after the request is not known for the slow loads: the page's timers were running about twice a second, and the check ran on them.
- **Frame rate:** sampled six times, it was 59, 2, 2, 1, 62 and 1 frames a second. The fast loads' rate was not measured. The cause is not established: the page had focus during one 2-frame sample and not during the 59-frame one.
- **For setup step 5:** "the pane is on screen" was not enough here, and the slowness was on the detail pages only, which fits the 2026-11-18 finding (streamed content waits for an animation frame). PR #43 fixed that cause; see setup step 5.
- **Not checked:** step 6 from the terminal (`replay.py request`; the dashboard's Replay button was used), the optional replay without `--fixed`, and `frontend/.env.local` (the two variables were passed on the command line). The browser kept only the last 35 or so API requests, all 2xx; the earlier ones were not read.
- **Setup step 4 moved to a production build on 2026-11-22 (UTC)** (Jayden and Adit's decision, after Adit's suggestion in #40). Step 4 and the "If something goes wrong" table now say to rebuild after changing `.env.local`; `/settings` says the same since PR #46 (a0ba982).

Not a rehearsal, but checked on 2026-11-18 by Jayden's Claude session:
- **Setup:** a production build of `main` at fe86776 (`npm run build && npm run start`, live mode), against a scratch backend on port 8001 with plain `seed.py`, the healthy, schema-change and ghost-invoice runs and one sandbox replay.
- **List pages:** the first page of Executions, Agents, Anomalies, Investigations and Replays match the API (81 / 3 / 3 / 3 / 1).
- **Filters clicked or typed in the UI:** executions by status and minimum duration, agents by health, anomalies by severity. Each went into the URL and came back after a reload.
- **Filters loaded from the URL only:** executions by agent, anomalies by status. The page applied them.
- **Anomaly actions:** Acknowledge, then Resolve, then Reopen, each changed the anomaly's status in the API, and the API's open count followed (3 → 2 → 3). The anomaly left the default Open view after Acknowledge. Overview showed 3 open after Reopen.
- **Other pages:** Overview, agent detail, and the trace page's Raw events and Input & output tabs all showed data.
- **Errors:** the only API error was the expected 404 for a run with no investigation.
- **Not checked:**
  - Executions page 2 (81 runs, 50 per page), sort, search, the Started range, and the Anomalies and Replays toggles.
  - The anomalies Agent and Rule filters, and the Investigations and Replays status filters.
  - The 24h / 7d / 30d switches, and `/traces`.
  - Resolve straight from Open, and what the page itself showed after Resolve and Reopen (only the API was checked).
  - Steps 1–7 in order on the production build (done on 2026-11-21; see the log above).

F12 (#28) live checks, 2026-11-23 (UTC), by Jayden's Claude session. Adit's side asked, through Jayden, for every item not checked on 2026-11-18 and for one authorized live replay; Jayden approved both. Jayden clicked in the pane a few times during the run.
- **Setup:** a production build of `main` at 3a170d2, live mode, against a scratch backend on port 8001 with its own database. Data: `seed.py --all`, then `seed.py --append --runs 4 --days 20`, so that the 7-day and 30-day windows differ (84 and 93 runs). `/settings` showed Live and port 8001 before any check. Each check below compared the request the page sent with the API's answer for the same query. For Overview, Executions, `/traces` and Replays the rows on screen were compared with that answer, id by id; for Anomalies and Investigations, the counts and the ids of the cards.
- **Overview:** 7d is the default; it loaded with `window=7d` and the API's numbers (84 runs, 98.8%). Clicking 24h and then 30d sent their `window` and showed the API's numbers (15 runs, 93.3%; 93 runs, 98.9%).
- **Executions:**
  - **Paging:** page 2 (`offset=50`) showed the API's 43 rows in order.
  - **Sort:** by duration, descending then ascending, matched the API and went back to page 1.
  - **Search:** "invoice" found the 30 Invoice Processor runs; a partial execution id found its one run (loaded from the URL).
  - **Started range:** "Last 24 hours" sent `started_after` and showed the 15 runs. A custom range, with both ends set in local time, was sent in UTC and showed the API's 33 runs. Choosing "Custom range…" from the menu did not take three times (two clicks on the option, then End and Return) and took on the fourth, a click at the option's position; the pane had been clicked by Jayden in between, and the cause is not established.
  - **Toggles:** with and without anomalies, 5 + 88 = 93. Replays only and originals only, 2 + 94 = 96.
- **`/traces`:** the recent list matched the API's latest 15. A malformed id stayed on `/traces` with the message giving the id format. A real id opened its trace. A well-formed id that does not exist opened the trace page's "This execution does not exist" state, after the API's 404.
- **Anomalies:**
  - **Filters:** the Agent filter (Support Triage, 4) and the Rule filter (Excessive retries, 2, with the Agent filter still set) matched the API.
  - **Resolve straight from Open:** the API had it `resolved`, and it left the Open view (2 → 1). With Resolved added to the status filter it came back, with a Reopen button.
  - **Acknowledge:** it left the view, because Acknowledged was not selected.
  - **Reopen:** the API had it `open`, and its card showed Open with Acknowledge and Resolve.
- **Investigations:** the status filter sent `status`, and Completed showed the 4. Failed showed the API's 0 and the "No investigations match these filters" state. Every investigation on scratch was completed, so the filter was not seen separating two non-empty sets.
- **Replays:** the status filter showed the 1 pending replay under Pending and the 2 completed ones under Completed, as the API listed them.
- **A replay page while its worker runs:**
  - **Before a worker:** a sandbox replay requested from the trace page sat on Pending, with "Waiting for a replay worker", until one was started.
  - **Once a worker started:** the page went Pending → Replaying → Completed, each seen once (Replaying for one 2-second poll), with "Same failure" and the comparison.
- **Replaying a running execution:**
  - **In the UI:** the trace page of an execution left running (created through `POST /executions`) shows Replay disabled, with "This run is still in progress. It can be replayed once it ends.", so the dashboard never sends that request.
  - **In the API:** the same request answered `409 conflict`, "Execution … is still running; it can be replayed once it ends."
- **The one live replay (authorized):** a healthy Invoice Processor run, requested from the dashboard with Live chosen and the authorization box ticked. The worker ran with `GHOSTWATCH_API_URL` set to port 8001.
  - The replay was recorded with `side_effects_authorized: true` and ended `completed`, "Both succeeded".
  - All three steps were `executed`, none recorded or blocked, including `submit_invoice`, the tool declared with side effects. In the replay's trace it returned `accepted` from the demo's fake invoice service, which only keeps a list in the worker's memory and uses no network.
- **Unexplained stall (setup step 5):** no page was found on its skeleton after its API request had answered. Content was read 0.5–6 s after each load, so a shorter stall would not have been seen. On the first Overview load after the server started, every API request had answered by 175 ms and the content was there at the first read (3.5 s). The pane was shown, but the page recorded no paint entries and drew about 3 frames a second, so when content appeared was not measured.
- **Not seen:** an investigation in any status but completed, and a failed replay, because the scratch data had none; and how the Replay dialog shows a 409, since the button is disabled before one can happen. The scratch database was dropped afterwards.

`docker compose down -v` was run on 2026-11-17 on Jayden's machine and the plain `seed.py` that followed printed exactly the expected output in setup step 3.
