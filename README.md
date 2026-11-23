# Ghostwatch

> Your agents say they're working. Ghostwatch makes sure they actually are.

Ghostwatch is an observability and reliability platform for AI agents. An agent reports what it does through a small SDK. Ghostwatch records every step, flags runs that look wrong, investigates failures from the recorded evidence, and can replay a failed run safely against its recording.

This README covers the backend, the Python SDK, the demo and the dashboard (`frontend/`).

## What you need

- Docker (for Postgres 16)
- [uv](https://docs.astral.sh/uv/) and Python 3.12

## Run it

```bash
cp .env.example .env
```
```bash
docker compose up -d
```
```bash
cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app
```

The API is at `http://localhost:8000/api/v1` and its live OpenAPI page at `http://localhost:8000/docs`. [docs/API.md](docs/API.md) is the reference, with examples captured from a real seeded server.

## Demo

Everything below goes through the SDK and the API. The demo never touches the database, and its three agents run on small deterministic fake services, so it needs no network and no API key.

Seed a week of history for the three demo agents:

```bash
cd demo && uv run python seed.py --all
```

Run one scenario live and see what Ghostwatch recorded (`list` shows them all):

```bash
cd demo && uv run python run_scenario.py schema-change
```

That run fails with `KeyError: 'results'`, and Ghostwatch confirms the root cause from the evidence. To replay it, start a replay worker in one terminal:

```bash
cd demo && uv run python replay.py worker --fixed
```

and request a sandbox replay in another, with the execution id the scenario printed:

```bash
cd demo && uv run python replay.py request <execution_id>
```

With `--fixed` the worker runs the agent with its parser fix and the outcome is `fixed`. Without it the agent runs as it shipped and the outcome is `same_failure`.

A sandbox replay never runs a tool with side effects. Calls the original run made return their recorded outputs. A call it never made runs only if it is a model call or a tool declared free of side effects; any other tool is blocked.

## Dashboard

The dashboard is a Next.js app in `frontend/`. It reads everything through the API; it never touches the database.

| Page | What it shows |
|---|---|
| Overview `/` | Run totals, success rate, average duration and open anomalies for the last 24 hours, 7 days or 30 days, a trend chart, agent health and recent runs |
| Agents `/agents` | Each agent's health, success rate and last run; an agent's page has its own numbers, runs and anomalies |
| Executions `/executions` | Every run, with filters and sorting that stay in the URL |
| Trace `/executions/{id}` | One run step by step: a waterfall, the raw event log, each step's input and output, and its investigation |
| Traces `/traces` | Open a trace by execution id, or pick a recent run |
| Anomalies `/anomalies` | What the detection rules flagged, most severe first, with the evidence; acknowledge, resolve or reopen each one |
| Investigations `/investigations` | Each report's facts (each linked to the step it comes from), hypotheses and root cause |
| Replays `/replays` | Replays and how each compares with the original run; a replay is requested from the trace page |
| Settings `/settings` | Where the data comes from, the backend's health and which investigation provider it uses |

The CI runs it on Node.js 24.

### Mock or live

- **Mock** (the default) serves the example data in `contract/fixtures/` from inside the browser. It needs no backend and sends it no request.
- **Live** reads the backend's API.

`/settings` says which one you are looking at. The mode and the API address go in `frontend/.env.local`; for live mode against the backend above:

```bash
NEXT_PUBLIC_API_MODE=live
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

Any mode other than `live` means mock. [.env.example](.env.example) has both variables under FRONTEND.

### Run it

```bash
cd frontend && npm ci && npm run build && npm run start
```

Open `http://localhost:3000`. Use `localhost`, not `127.0.0.1`: the backend accepts browser requests only from the origins in `CORS_ORIGINS` (`.env`), which defaults to `http://localhost:3000`.

Both variables are fixed when the app is built. After changing `.env.local`, run `npm run build` again before `npm run start`; restarting alone keeps the old values. `npm run dev` starts a development server instead, which reads `.env.local` when it starts.

### Tests

```bash
cd frontend && npm run typecheck && npm run lint && npm test
```
```bash
cd frontend && npm run test:e2e
```

The end-to-end tests build the app in mock mode, serve it on port 3100 and drive it with Playwright: Edge on Windows, Playwright's Chromium elsewhere (install it once with `npx playwright install chromium`). They leave that mock build in `frontend/.next`, so run `npm run build` again before `npm run start` in live mode; `/settings` shows Mock until you do.

## Investigation providers

Investigations run on `LLM_PROVIDER=rule_based` by default. That provider is deterministic code: it needs no API key, makes no network calls and costs nothing. The demo, the seeded data, the tests and every example in `docs/API.md` were produced with it.

`LLM_PROVIDER=fable` is optional. It asks Anthropic's Claude Fable model to propose additional hypotheses, which must cite the recorded facts and can never mark a root cause as confirmed. It needs `ANTHROPIC_API_KEY` in `.env`, and each investigation is a paid API call. This provider has been tested with a fake client only; it has not been run against the real API.

Either way, facts, anomaly detection and confirmed root causes come from deterministic code, and each investigation records which provider produced it.

## Tests

```bash
cd backend && uv run ruff check . && uv run pytest -q
```
```bash
cd sdk/python && uv run pytest -q
```

The backend tests need the compose Postgres running; they use a separate `ghostwatch_test` database.

## Where things are

| Path | What |
|---|---|
| `contract/API_CONTRACT.md` | The API contract. If code and contract disagree, the code is wrong. |
| `backend/` | FastAPI service: ingestion, traces, stats, anomalies, investigations, replays |
| `sdk/python/` | The `ghostwatch` SDK: zero dependencies, never slows down or breaks the agent |
| `demo/` | Three demo agents, fake services, seeding, scenarios, the replay worker |
| `frontend/` | The dashboard (Next.js) |
| `docs/API.md` | API reference |
| `PROJECT_PLAN.md`, `CONTRIBUTING.md` | Plan, ownership and how to contribute |

## Limits to know about

- Authentication is a single ingestion key for the endpoints the SDK writes to. Read endpoints are unauthenticated and meant for localhost.
- `cost_usd` uses Anthropic's published list prices for models in the price table and is unknown (`null`) for anything else, including the demo's fake model.
