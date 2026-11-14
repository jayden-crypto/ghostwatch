"""Regenerate docs/API.md, with every example captured from a running, seeded server.

Usage (from backend/):
    uv run python -m scripts.api_docs [base_url]

The server should hold demo data (`cd demo && uv run python seed.py --all`), because the examples
show the schema-change failure and the ghost-completion run. The script makes a few real writes:
it re-registers the research-assistant agent and records one short execution.

Nothing in the generated examples is written by hand. Responses are shortened mechanically (see
`shorten`), and the document says so.
"""

import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2

from app.config import REPO_ROOT, get_settings
from app.timeutil import format_timestamp

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api/v1"
DOCUMENTED_BASE_URL = "http://localhost:8000/api/v1"
KEY = get_settings().ghostwatch_api_key
OUTPUT = REPO_ROOT / "docs" / "API.md"
MAX_STRING = 260
MAX_SCALARS = 8  # lists of plain values (step names, loc paths) are shown nearly whole

client = httpx2.Client(base_url=BASE_URL, timeout=30)


def shorten(value: Any, keep: int) -> Any:
    """Lists of objects keep their first `keep` items plus a count of the rest; long strings are cut."""
    if isinstance(value, list):
        limit = keep if any(isinstance(item, dict) for item in value) else MAX_SCALARS
        kept = [shorten(item, keep) for item in value[:limit]]
        return kept + ([f"… {len(value) - limit} more"] if len(value) > limit else [])
    if isinstance(value, dict):
        return {key: shorten(item, keep) for key, item in value.items()}
    if isinstance(value, str) and len(value) > MAX_STRING:
        return value[:MAX_STRING] + "…"
    return value


def example(method: str, path: str, *, body: Any = None, auth: bool = False, keep: int = 1) -> str:
    """Run the request for real and render it as a curl command followed by the shortened response."""
    headers = {"Authorization": f"Bearer {KEY}"} if auth else {}
    response = client.request(method, path, json=body, headers=headers)
    verb = "" if method == "GET" else f" -X {method}"
    command = [f'curl -s{verb} "{DOCUMENTED_BASE_URL}{path}"']
    if auth:
        command.append('-H "Authorization: Bearer $GHOSTWATCH_API_KEY"')
    if body is not None:
        command.append("-H 'Content-Type: application/json'")
        command.append(f"-d '{json.dumps(shorten(body, 4), ensure_ascii=False)}'")
    shown = json.dumps(shorten(response.json(), keep), indent=1, ensure_ascii=False)
    return f"```bash\n{' \\\n  '.join(command)}\n```\n\n`{response.status_code}`\n\n```json\n{shown}\n```"


def first(path: str) -> dict[str, Any]:
    items = client.get(path).json()["items"]
    if not items:
        raise SystemExit(
            f"GET {path} returned nothing. Seed the server first: cd demo && uv run python seed.py --all"
        )
    return items[0]


def build() -> str:
    failed = first("/executions?status=failed&q=Research&limit=1")
    ghost = first("/anomalies?type=ghost_completion&limit=1")
    research = first("/agents?q=research-assistant")

    started_at = datetime.now(UTC) - timedelta(seconds=2)

    def at(offset_ms: int) -> str:
        return format_timestamp(started_at + timedelta(milliseconds=offset_ms))

    register = example(
        "POST",
        "/agents",
        body={"name": "Research Assistant", "slug": "research-assistant", "framework": "custom"},
        auth=True,
    )
    create_body = {
        "agent_id": research["id"],
        "input": {"question": "How do teams trace what an AI agent did?"},
        "config": {"model": "demo-llm-1", "expected_steps": ["web_search"]},
        "tags": ["docs"],
        "started_at": at(0),
    }
    created = client.post("/executions", json=create_body, headers={"Authorization": f"Bearer {KEY}"})
    execution_id = created.json()["id"]
    create = (
        '```bash\ncurl -s -X POST "' + DOCUMENTED_BASE_URL + '/executions" \\\n'
        '  -H "Authorization: Bearer $GHOSTWATCH_API_KEY" \\\n'
        "  -H 'Content-Type: application/json' \\\n"
        f"  -d '{json.dumps(create_body)}'\n```\n\n`{created.status_code}`\n\n"
        f"```json\n{json.dumps(shorten(created.json(), 1), indent=1)}\n```"
    )
    step_id = f"stp_{uuid.uuid4().hex}"
    events = {
        "events": [
            {
                "seq": 1,
                "type": "step.started",
                "timestamp": at(10),
                "payload": {
                    "step_id": step_id,
                    "name": "web_search",
                    "step_type": "tool_call",
                    "tool_name": "web_search",
                    "input": {"query": "agent tracing"},
                },
            },
            {
                "seq": 2,
                "type": "step.completed",
                "timestamp": at(380),
                "payload": {"step_id": step_id, "output": {"results": [], "total": 0}},
            },
            {
                "seq": 3,
                "type": "execution.completed",
                "timestamp": at(400),
                "payload": {"output": {"answer": "…"}},
            },
        ]
    }
    events_path = f"/executions/{execution_id}/events"
    late = {
        "events": [
            {
                "seq": 4,
                "type": "step.started",
                "timestamp": at(900),
                "payload": {"step_id": f"stp_{uuid.uuid4().hex}", "name": "late", "step_type": "custom"},
            }
        ]
    }
    examples = {
        "health": example("GET", "/health"),
        "register": register,
        "agents": example("GET", "/agents?health=failing,degraded&sort=name"),
        "create": create,
        "ingest": example("POST", events_path, body=events, auth=True, keep=3),
        "ingest_again": example("POST", events_path, body=events, auth=True, keep=3),
        "ingest_late": example("POST", events_path, body=late, auth=True),
        "executions": example("GET", "/executions?status=failed&sort=-started_at&limit=1"),
        "trace": example("GET", f"/executions/{failed['id']}/trace", keep=3),
        "events": example("GET", f"/executions/{failed['id']}/events?limit=2", keep=2),
        "overview": example("GET", "/stats/overview?window=7d"),
        "timeseries": example("GET", "/stats/timeseries?window=7d", keep=2),
        "anomalies": example("GET", "/anomalies?severity=critical&limit=1"),
        "investigation": example("GET", f"/investigations/{failed['id']}", keep=2),
        "investigate": example("POST", f"/investigations/{ghost['execution_id']}", keep=1),
        "not_found": example("GET", "/executions/exe_00000000000000000000000000000000"),
        "unauthorized": example("POST", "/agents", body={"name": "X", "slug": "x"}),
        "invalid": example("POST", "/agents", body={"name": "X", "slug": "Not A Slug"}, auth=True),
        "bad_sort": example("GET", "/executions?sort=step_count"),
    }
    document = TEMPLATE
    for name, rendered in examples.items():
        placeholder = "{{" + name + "}}"
        if placeholder not in document:
            raise SystemExit(f"example {name!r} is not used in the template")
        document = document.replace(placeholder, rendered)
    if "{{" in document:
        raise SystemExit("the template has a placeholder with no example")
    return document


TEMPLATE = """\
# Ghostwatch API

Human-readable reference for the backend. Two other documents matter more than this one when they disagree:

- [`contract/API_CONTRACT.md`](../contract/API_CONTRACT.md) is the source of truth for every request and response shape.
- `http://localhost:8000/docs` is the live OpenAPI page, generated from the running code.

Every example below is a real response from a local instance seeded with `demo/seed.py --all`, captured by
`backend/scripts/api_docs.py`. Responses are shortened mechanically and in no other way: lists show their
first items followed by `"… N more"`, and long strings are cut with `…`.

## Running it

```bash
docker compose up -d
```
```bash
cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app
```
```bash
cd demo && uv run python seed.py --all
```

Base URL: `http://localhost:8000/api/v1`.

## Conventions

| Concern | Rule |
|---|---|
| Keys | `snake_case` in both directions |
| Ids | Opaque strings: a prefix (`agt_`, `exe_`, `stp_`, `evt_`, `anm_`, `inv_`, `rpl_`) and 32 hex characters |
| Timestamps | ISO 8601, UTC, milliseconds, `Z`: `2026-11-14T10:32:05.123Z`. Requests may use any UTC offset; epoch numbers and times without an offset are rejected |
| Durations | Integer milliseconds, in fields ending `_ms` |
| Missing values | A field with no value is `null`; it is never left out. Unknown tokens and cost are `null`, never `0` |
| Pagination | `limit` (default 50, max 200) and `offset` (default 0). Lists return `{items, total, limit, offset}`; `total` counts all matches |
| Sorting | `sort=field` or `sort=-field` (descending). Unknown values sort last in both directions |
| Large payloads | Any `input`, `output` or `metadata` over 64 KB is stored as `{"_truncated": true, "original_bytes": <int>, "preview": "<first 2000 chars>"}`. Error messages, stack traces and log messages over 64 KB stay strings, cut to 64 KB with a `[truncated: N bytes in total]` note |
| Unknown ids | An id in a path that matches nothing is a `404`, whatever it looks like |

## Authentication

This is an MVP limitation, stated plainly: the endpoints an SDK writes to (marked 🔑) require
`Authorization: Bearer <GHOSTWATCH_API_KEY>`. Every read endpoint is unauthenticated and intended for
localhost only. Do not expose this API to a network you do not trust.

## Errors

Every non-2xx response has the same shape.

{{not_found}}

| HTTP | `code` | When |
|---|---|---|
| 400 | `bad_request` | `sort` names a field the endpoint cannot sort by |
| 401 | `unauthorized` | 🔑 endpoint called without the key, or with the wrong one |
| 404 | `not_found` | Unknown id, or unknown route |
| 409 | `execution_already_terminal` | A new non-log event for an execution that has ended |
| 409 | `conflict` | Investigating an execution that is still running |
| 422 | `validation_error` | `details` is a list of `{loc, msg}`; `loc` is a path such as `["body", "slug"]` |
| 500 | `internal_error` | Unexpected failure; the body never contains a stack trace |

{{unauthorized}}

{{invalid}}

{{bad_sort}}

## Health

### `GET /health`

Always `200` while the process is up. `database` comes from a real query. `llm_configured` says whether the
configured investigation provider can run: `rule_based` always can, `fable` only with `ANTHROPIC_API_KEY` set.
`llm_model` is `null` for `rule_based`.

{{health}}

## Agents

Contract §3. `stats` is computed from stored executions and anomalies on every request.

- `success_rate` = completed / (completed + failed + timed_out) over all of the agent's executions; `null` when none has finished.
- `health` uses the agent's last 20 terminal executions and its open anomalies: `failing` below 50 % success or with an open `critical` anomaly; `degraded` below 90 % or with an open `high` anomaly; `idle` with no executions; otherwise `healthy`. So an agent can show a high all-time `success_rate` and still be `failing`.

### `POST /agents` 🔑

Registers an agent, or updates it if the slug exists. `201` when created, `200` when updated. Safe to call on
every start. On an update, fields left out keep their stored value; an explicit `null` clears one.

| Body field | Type | Notes |
|---|---|---|
| `name` | string | Required |
| `slug` | string | Required, `[a-z0-9-]+`, unique |
| `description`, `framework` | string or null | Optional |
| `metadata` | object | Optional |

{{register}}

### `GET /agents`

| Query | Notes |
|---|---|
| `q` | Name or slug contains (case-insensitive) |
| `health` | Comma-separated: `healthy`, `degraded`, `failing`, `idle` |
| `sort` | `name` (default) or `created_at` |
| `limit`, `offset` | Pagination |

{{agents}}

### `GET /agents/{agent_id}`

One agent, in the same shape as a list item. `404` if unknown.

## Executions

Contract §4.

### `POST /executions` 🔑

Starts a run in status `running`. Everything after this arrives as events.

| Body field | Type | Notes |
|---|---|---|
| `agent_id` | id | Required. `404` if unknown |
| `input` | any JSON | The run's input |
| `config` | object | `model`, `params`, `expected_steps`, `timeout_ms`, plus any extra keys. All four known keys are always present in responses |
| `tags` | string[] | Optional |
| `started_at` | timestamp | Optional; defaults to the server's clock |
| `replay_of`, `replay_id` | id | Set by the replay worker |

`config.expected_steps` lists step names that must complete for the run to count as done (the ghost-completion
rule). `config.timeout_ms` is how long the run may send nothing before it is timed out (default 300000).

{{create}}

### `GET /executions`

All filters combine with AND.

| Query | Notes |
|---|---|
| `agent_id` | Exact |
| `status` | Comma-separated: `running`, `completed`, `failed`, `timed_out` |
| `started_after` | Inclusive |
| `started_before` | Exclusive |
| `min_duration_ms`, `max_duration_ms` | Running executions have no duration and are left out when either is set |
| `has_anomaly` | `true` or `false` |
| `is_replay` | `true` or `false` |
| `replay_of` | Executions that replay this one |
| `q` | Execution id prefix, or part of the agent name |
| `sort` | `started_at` (default `-started_at`), `duration_ms`, `tokens_total`, `cost_usd` |
| `limit`, `offset` | Pagination |

{{executions}}

### `GET /executions/{execution_id}`

The summary plus `input`, `output`, `config`, `tokens_input`, `tokens_output`, `tags` and `replay_ids`.

## Event ingestion

Contract §5. Events are the only way an execution's state changes. The `events` table is append-only and is
the evidence everything else is derived from.

### `POST /executions/{execution_id}/events` 🔑

Body: `{"events": [...]}` with 1 to 500 events. Each event has `seq` (starts at 1, increases per execution),
`type`, `timestamp` and a `payload` whose shape depends on the type (contract §5).

- Events are applied in `seq` order, whatever their order in the batch.
- A `seq` already stored for the execution is counted in `duplicates` and skipped. Resending a batch is
  always safe, including after the execution has ended.
- A batch is all-or-nothing: if any event is rejected, none is stored.
- `step.completed` or `step.failed` for a step that was never started in this execution, or has already
  ended, is a `422`. A step id can be started once.
- After a terminal event, a new non-`log` event is a `409 execution_already_terminal`.
- A terminal event sets `ended_at`, `duration_ms` (from the client's timestamps, never negative) and token
  totals, runs the anomaly rules, and queues an investigation if the run failed, timed out, or raised an
  anomaly of `high` severity or above. Steps still running at that point are left running: that is evidence.

{{ingest}}

Sending the same batch again:

{{ingest_again}}

A new step event after the execution has ended:

{{ingest_late}}

## Traces

Contract §6.

### `GET /executions/{execution_id}/trace`

The execution, its steps as a flat list sorted by `ordinal`, the anomalies raised on it, and `event_count`.
Build the tree from `parent_step_id`. `depth` and `offset_ms` (start relative to the execution's start) are
computed by the backend. A step whose parent is not in the execution is laid out as a root.

This is the schema-change failure from the demo: `web_search` returned `data` and `meta`, and
`parse_results` asked for `results`.

{{trace}}

### `GET /executions/{execution_id}/events`

The raw event log in `seq` order, exactly as stored. Paginated.

{{events}}

## Stats

Contract §7. A window is a whole number of UTC-aligned buckets ending with the current one: `24h` is this hour
and the 23 before it, `7d` is today and the 6 days before it, `30d` likewise.

### `GET /stats/overview?window=24h|7d|30d`

Default `7d`. Counts executions started inside the window. `success_rate` and `avg_duration_ms` are `null`
when nothing has finished. `total_agents` and `open_anomalies` are current totals, not limited to the window.

{{overview}}

### `GET /stats/timeseries?window=&bucket=hour|day&agent_id=`

One point per bucket, oldest first, with zeros where nothing ran. `bucket` defaults to `hour` for `24h` and
`day` otherwise. With the default bucket the points add up to the overview's totals. Running executions are
counted in the overview but are not in the points.

{{timeseries}}

## Anomalies

Contract §8. Eight deterministic rules run when an execution ends: `duration_spike`, `token_spike`,
`repeated_tool_failure`, `excessive_retries`, `repeated_timeouts`, `ghost_completion`, `stale_execution`,
`unexpected_pattern`. Their thresholds are constants in `backend/app/services/anomaly/thresholds.py`.

- The baseline is the agent's last 20 completed, non-replay executions. Rules that need it are skipped below 5 runs.
- `explanation` states the observed value, the baseline figures and the threshold formula.
- Every `evidence` item points at a stored step or execution through `ref_id` and copies the value found there.
- `stale_execution` is raised by a background sweeper: a running execution that sends no event for
  `config.timeout_ms` is timed out through an appended `execution.timed_out` event.
- Agent-level anomalies (`repeated_timeouts`, and `repeated_tool_failure` across executions) carry the id of
  the execution that completed the pattern.

### `GET /anomalies`

| Query | Notes |
|---|---|
| `agent_id`, `execution_id` | Exact |
| `type`, `severity`, `status` | Comma-separated lists |
| `sort` | `detected_at` (default `-detected_at`) |
| `limit`, `offset` | Pagination |

{{anomalies}}

### `GET /anomalies/{anomaly_id}`

One anomaly. `404` if unknown.

## Investigations

Contract §9. A report separates three things:

- **Facts** are produced by code from stored data. Each has evidence pointing at the step, execution or
  anomaly it came from, with excerpts copied verbatim.
- **Hypotheses** must cite facts. Hypotheses from a deterministic signature have confidence `high`. With
  `LLM_PROVIDER=fable`, the model may add more; any that cites a fact or step that does not exist is dropped
  and noted under `evidence_gaps`.
- **`root_cause.status`** is `confirmed` only when a deterministic signature matched
  (`missing_key_in_upstream_output`, `retry_exhaustion`, `tool_http_error`, `timeout_in_step`,
  `ghost_completion`). A model's hypothesis is `probable` at most. With no signature and no surviving
  hypothesis it is `insufficient_evidence`.

`provider` says who contributed the hypotheses. If the model call fails or no key is configured, the report is
produced by `rule_based`, `provider` says so, and `evidence_gaps` gives the reason. `summary` is always a
deterministic template.

Investigations start automatically when an execution fails or times out (`auto_failure`), or raises an anomaly
of `high` severity or above (`auto_anomaly`).

### `GET /investigations/{execution_id}`

The latest investigation of the execution, or `404`. `report` is `null` until `status` is `completed`.
Poll every 2 s while `status` is `queued` or `running`.

{{investigation}}

### `POST /investigations/{execution_id}`

Body: `{"force": true}` or nothing. Returns `202` with a queued investigation and runs it in the background.
If one is already queued or running, that one is returned. If a completed one exists, it is returned with
`200` unless `force` is set. `409 conflict` while the execution is still running.

{{investigate}}

### `GET /investigations`

`Page<Investigation>` with reports, newest first. Query: `status` (comma-separated), `agent_id`, `sort`
(`created_at`), `limit`, `offset`.

## Not implemented

These are in the contract and are not built yet. They return the `404` envelope.

| Endpoint | Status |
|---|---|
| `PATCH /anomalies/{anomaly_id}` | Not implemented (P1) |
| `POST /executions/{execution_id}/replay` | Not implemented (P1) |
| `GET /replays`, `GET /replays/{replay_id}` | Not implemented (P1) |
| `POST /replays/{replay_id}/claim` | Not implemented (P1) |

`cost_usd` is always `null` for now: the pricing table (P1) is not built, and a price is never guessed.
"""

if __name__ == "__main__":
    OUTPUT.write_text(build())
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
