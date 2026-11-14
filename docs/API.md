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

```bash
curl -s "http://localhost:8000/api/v1/executions/exe_00000000000000000000000000000000"
```

`404`

```json
{
 "error": {
  "code": "not_found",
  "message": "Execution exe_00000000000000000000000000000000 does not exist.",
  "details": null
 }
}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `bad_request` | `sort` names a field the endpoint cannot sort by |
| 401 | `unauthorized` | 🔑 endpoint called without the key, or with the wrong one |
| 404 | `not_found` | Unknown id, or unknown route |
| 409 | `execution_already_terminal` | A new non-log event for an execution that has ended |
| 409 | `conflict` | Investigating an execution that is still running |
| 422 | `validation_error` | `details` is a list of `{loc, msg}`; `loc` is a path such as `["body", "slug"]` |
| 500 | `internal_error` | Unexpected failure; the body never contains a stack trace |

```bash
curl -s -X POST "http://localhost:8000/api/v1/agents" \
  -H 'Content-Type: application/json' \
  -d '{"name": "X", "slug": "x"}'
```

`401`

```json
{
 "error": {
  "code": "unauthorized",
  "message": "Missing or invalid API key.",
  "details": null
 }
}
```

```bash
curl -s -X POST "http://localhost:8000/api/v1/agents" \
  -H "Authorization: Bearer $GHOSTWATCH_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"name": "X", "slug": "Not A Slug"}'
```

`422`

```json
{
 "error": {
  "code": "validation_error",
  "message": "Request validation failed.",
  "details": [
   {
    "loc": [
     "body",
     "slug"
    ],
    "msg": "String should match pattern '^[a-z0-9-]+$'"
   }
  ]
 }
}
```

```bash
curl -s "http://localhost:8000/api/v1/executions?sort=step_count"
```

`400`

```json
{
 "error": {
  "code": "bad_request",
  "message": "Cannot sort by 'step_count'. Allowed: cost_usd, duration_ms, started_at, tokens_total (prefix with - for descending).",
  "details": null
 }
}
```

## Health

### `GET /health`

Always `200` while the process is up. `database` comes from a real query. `llm_configured` says whether the
configured investigation provider can run: `rule_based` always can, `fable` only with `ANTHROPIC_API_KEY` set.
`llm_model` is `null` for `rule_based`.

```bash
curl -s "http://localhost:8000/api/v1/health"
```

`200`

```json
{
 "status": "ok",
 "version": "0.1.0",
 "database": "ok",
 "llm_provider": "rule_based",
 "llm_configured": true,
 "llm_model": null
}
```

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

```bash
curl -s -X POST "http://localhost:8000/api/v1/agents" \
  -H "Authorization: Bearer $GHOSTWATCH_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"name": "Research Assistant", "slug": "research-assistant", "framework": "custom"}'
```

`200`

```json
{
 "id": "agt_1e4e2964568d4f6b932088e917020439",
 "name": "Research Assistant",
 "slug": "research-assistant",
 "description": "Answers a question from web search results.",
 "framework": "custom",
 "metadata": {},
 "created_at": "2026-11-14T20:38:34.836Z",
 "stats": {
  "total_executions": 28,
  "completed": 27,
  "failed": 1,
  "timed_out": 0,
  "running": 0,
  "success_rate": 0.9642857142857143,
  "avg_duration_ms": 781,
  "open_anomalies": 0,
  "last_execution": {
   "id": "exe_0e6892c38dcb45c0a7c73d5e69cb2a5a",
   "agent_id": "agt_1e4e2964568d4f6b932088e917020439",
   "agent_name": "Research Assistant",
   "status": "completed",
   "started_at": "2026-11-14T20:39:08.214Z",
   "ended_at": "2026-11-14T20:39:08.614Z",
   "duration_ms": 400,
   "step_count": 1,
   "tokens_total": null,
   "cost_usd": null,
   "anomaly_count": 0,
   "has_investigation": false,
   "replay_of": null,
   "error": null
  },
  "health": "healthy"
 }
}
```

### `GET /agents`

| Query | Notes |
|---|---|
| `q` | Name or slug contains (case-insensitive) |
| `health` | Comma-separated: `healthy`, `degraded`, `failing`, `idle` |
| `sort` | `name` (default) or `created_at` |
| `limit`, `offset` | Pagination |

```bash
curl -s "http://localhost:8000/api/v1/agents?health=failing,degraded&sort=name"
```

`200`

```json
{
 "items": [
  {
   "id": "agt_ce1157da711e4712be2c6edfe8272a22",
   "name": "Invoice Processor",
   "slug": "invoice-processor",
   "description": "Extracts invoice fields, validates them and submits the invoice for payment.",
   "framework": "custom",
   "metadata": {},
   "created_at": "2026-11-14T20:38:35.625Z",
   "stats": {
    "total_executions": 26,
    "completed": 26,
    "failed": 0,
    "timed_out": 0,
    "running": 0,
    "success_rate": 1.0,
    "avg_duration_ms": 507,
    "open_anomalies": 1,
    "last_execution": {
     "id": "exe_e5688ee8a1c54100b1e88ffb804a8498",
     "agent_id": "agt_ce1157da711e4712be2c6edfe8272a22",
     "agent_name": "Invoice Processor",
     "status": "completed",
     "started_at": "2026-11-14T20:18:34.829Z",
     "ended_at": "2026-11-14T20:18:35.052Z",
     "duration_ms": 223,
     "step_count": 2,
     "tokens_total": null,
     "cost_usd": null,
     "anomaly_count": 1,
     "has_investigation": true,
     "replay_of": null,
     "error": null
    },
    "health": "failing"
   }
  },
  "… 1 more"
 ],
 "total": 2,
 "limit": 50,
 "offset": 0
}
```

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

```bash
curl -s -X POST "http://localhost:8000/api/v1/executions" \
  -H "Authorization: Bearer $GHOSTWATCH_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"agent_id": "agt_1e4e2964568d4f6b932088e917020439", "input": {"question": "How do teams trace what an AI agent did?"}, "config": {"model": "demo-llm-1", "expected_steps": ["web_search"]}, "tags": ["docs"], "started_at": "2026-11-14T20:39:29.748Z"}'
```

`201`

```json
{
 "id": "exe_cb3ebc646e3145b89f76795a4955d3d5",
 "agent_id": "agt_1e4e2964568d4f6b932088e917020439",
 "agent_name": "Research Assistant",
 "status": "running",
 "started_at": "2026-11-14T20:39:29.748Z",
 "ended_at": null,
 "duration_ms": null,
 "step_count": 0,
 "tokens_total": null,
 "cost_usd": null,
 "anomaly_count": 0,
 "has_investigation": false,
 "replay_of": null,
 "error": null,
 "input": {
  "question": "How do teams trace what an AI agent did?"
 },
 "output": null,
 "config": {
  "model": "demo-llm-1",
  "params": {},
  "expected_steps": [
   "web_search"
  ],
  "timeout_ms": null
 },
 "tokens_input": null,
 "tokens_output": null,
 "tags": [
  "docs"
 ],
 "replay_ids": []
}
```

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

```bash
curl -s "http://localhost:8000/api/v1/executions?status=failed&sort=-started_at&limit=1"
```

`200`

```json
{
 "items": [
  {
   "id": "exe_40d8319b2ac749a7aae6c45d29129ead",
   "agent_id": "agt_1e4e2964568d4f6b932088e917020439",
   "agent_name": "Research Assistant",
   "status": "failed",
   "started_at": "2026-11-14T20:08:34.829Z",
   "ended_at": "2026-11-14T20:08:35.215Z",
   "duration_ms": 386,
   "step_count": 3,
   "tokens_total": null,
   "cost_usd": null,
   "anomaly_count": 0,
   "has_investigation": true,
   "replay_of": null,
   "error": {
    "type": "KeyError",
    "message": "'results'",
    "stacktrace": "Traceback (most recent call last):\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 56, in run\n    sources = parse_results(payload)\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 42, in parse_…"
   }
  }
 ],
 "total": 1,
 "limit": 1,
 "offset": 0
}
```

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

```bash
curl -s -X POST "http://localhost:8000/api/v1/executions/exe_cb3ebc646e3145b89f76795a4955d3d5/events" \
  -H "Authorization: Bearer $GHOSTWATCH_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"events": [{"seq": 1, "type": "step.started", "timestamp": "2026-11-14T20:39:29.758Z", "payload": {"step_id": "stp_b72aef838d024908ad7a0ca685a4de2c", "name": "web_search", "step_type": "tool_call", "tool_name": "web_search", "input": {"query": "agent tracing"}}}, {"seq": 2, "type": "step.completed", "timestamp": "2026-11-14T20:39:30.128Z", "payload": {"step_id": "stp_b72aef838d024908ad7a0ca685a4de2c", "output": {"results": [], "total": 0}}}, {"seq": 3, "type": "execution.completed", "timestamp": "2026-11-14T20:39:30.148Z", "payload": {"output": {"answer": "…"}}}]}'
```

`202`

```json
{
 "accepted": 3,
 "duplicates": 0,
 "execution_status": "completed"
}
```

Sending the same batch again:

```bash
curl -s -X POST "http://localhost:8000/api/v1/executions/exe_cb3ebc646e3145b89f76795a4955d3d5/events" \
  -H "Authorization: Bearer $GHOSTWATCH_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"events": [{"seq": 1, "type": "step.started", "timestamp": "2026-11-14T20:39:29.758Z", "payload": {"step_id": "stp_b72aef838d024908ad7a0ca685a4de2c", "name": "web_search", "step_type": "tool_call", "tool_name": "web_search", "input": {"query": "agent tracing"}}}, {"seq": 2, "type": "step.completed", "timestamp": "2026-11-14T20:39:30.128Z", "payload": {"step_id": "stp_b72aef838d024908ad7a0ca685a4de2c", "output": {"results": [], "total": 0}}}, {"seq": 3, "type": "execution.completed", "timestamp": "2026-11-14T20:39:30.148Z", "payload": {"output": {"answer": "…"}}}]}'
```

`202`

```json
{
 "accepted": 0,
 "duplicates": 3,
 "execution_status": "completed"
}
```

A new step event after the execution has ended:

```bash
curl -s -X POST "http://localhost:8000/api/v1/executions/exe_cb3ebc646e3145b89f76795a4955d3d5/events" \
  -H "Authorization: Bearer $GHOSTWATCH_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"events": [{"seq": 4, "type": "step.started", "timestamp": "2026-11-14T20:39:30.648Z", "payload": {"step_id": "stp_d601cb4d30a04166b94669c8768573a0", "name": "late", "step_type": "custom"}}]}'
```

`409`

```json
{
 "error": {
  "code": "execution_already_terminal",
  "message": "Execution exe_cb3ebc646e3145b89f76795a4955d3d5 is already completed; only log events are accepted.",
  "details": {
   "execution_status": "completed",
   "rejected_seq": 4
  }
 }
}
```

## Traces

Contract §6.

### `GET /executions/{execution_id}/trace`

The execution, its steps as a flat list sorted by `ordinal`, the anomalies raised on it, and `event_count`.
Build the tree from `parent_step_id`. `depth` and `offset_ms` (start relative to the execution's start) are
computed by the backend. A step whose parent is not in the execution is laid out as a root.

This is the schema-change failure from the demo: `web_search` returned `data` and `meta`, and
`parse_results` asked for `results`.

```bash
curl -s "http://localhost:8000/api/v1/executions/exe_40d8319b2ac749a7aae6c45d29129ead/trace"
```

`200`

```json
{
 "execution": {
  "id": "exe_40d8319b2ac749a7aae6c45d29129ead",
  "agent_id": "agt_1e4e2964568d4f6b932088e917020439",
  "agent_name": "Research Assistant",
  "status": "failed",
  "started_at": "2026-11-14T20:08:34.829Z",
  "ended_at": "2026-11-14T20:08:35.215Z",
  "duration_ms": 386,
  "step_count": 3,
  "tokens_total": null,
  "cost_usd": null,
  "anomaly_count": 0,
  "has_investigation": true,
  "replay_of": null,
  "error": {
   "type": "KeyError",
   "message": "'results'",
   "stacktrace": "Traceback (most recent call last):\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 56, in run\n    sources = parse_results(payload)\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 42, in parse_…"
  },
  "input": {
   "question": "How do teams trace what an AI agent did?"
  },
  "output": null,
  "config": {
   "model": "demo-llm-1",
   "params": {
    "max_results": 3
   },
   "expected_steps": [
    "web_search",
    "parse_results",
    "summarize"
   ],
   "timeout_ms": null
  },
  "tokens_input": null,
  "tokens_output": null,
  "tags": [
   "demo"
  ],
  "replay_ids": []
 },
 "steps": [
  {
   "id": "stp_d9d5f7795a20471bab61ebaf56f73017",
   "execution_id": "exe_40d8319b2ac749a7aae6c45d29129ead",
   "parent_step_id": null,
   "ordinal": 1,
   "depth": 0,
   "name": "plan",
   "type": "reasoning",
   "status": "completed",
   "started_at": "2026-11-14T20:08:34.830Z",
   "ended_at": "2026-11-14T20:08:34.831Z",
   "duration_ms": 1,
   "offset_ms": 1,
   "input": {
    "question": "How do teams trace what an AI agent did?"
   },
   "output": {
    "query": "how do teams trace what an ai agent did"
   },
   "error": null,
   "tool_name": null,
   "model": null,
   "tokens_input": null,
   "tokens_output": null,
   "attempt": 1,
   "metadata": {}
  },
  {
   "id": "stp_2c45922b0984485ea95593c00a2b91e3",
   "execution_id": "exe_40d8319b2ac749a7aae6c45d29129ead",
   "parent_step_id": null,
   "ordinal": 2,
   "depth": 0,
   "name": "web_search",
   "type": "tool_call",
   "status": "completed",
   "started_at": "2026-11-14T20:08:34.832Z",
   "ended_at": "2026-11-14T20:08:35.212Z",
   "duration_ms": 380,
   "offset_ms": 3,
   "input": {
    "query": "how do teams trace what an ai agent did"
   },
   "output": {
    "data": [
     {
      "url": "https://example.test/agent-observability",
      "title": "Agent observability: tracing every step",
      "snippet": "Tracing records each tool call and model call an agent makes, with inputs and outputs."
     },
     {
      "url": "https://example.test/silent-failures",
      "title": "Why silent failures are the hardest agent bugs",
      "snippet": "An agent can report success while skipping the step that mattered."
     },
     {
      "url": "https://example.test/replay",
      "title": "Replaying agent runs against recorded inputs",
      "snippet": "Deterministic replay turns a production failure into a local test case."
     }
    ],
    "meta": {
     "total": 3,
     "api_version": "2026-11"
    }
   },
   "error": null,
   "tool_name": "web_search",
   "model": null,
   "tokens_input": null,
   "tokens_output": null,
   "attempt": 1,
   "metadata": {
    "side_effects": false
   }
  },
  {
   "id": "stp_52c2ec9b42604237b472bd57e6ecc406",
   "execution_id": "exe_40d8319b2ac749a7aae6c45d29129ead",
   "parent_step_id": null,
   "ordinal": 3,
   "depth": 0,
   "name": "parse_results",
   "type": "reasoning",
   "status": "failed",
   "started_at": "2026-11-14T20:08:35.213Z",
   "ended_at": "2026-11-14T20:08:35.214Z",
   "duration_ms": 1,
   "offset_ms": 384,
   "input": {
    "response_keys": [
     "data",
     "meta"
    ]
   },
   "output": null,
   "error": {
    "type": "KeyError",
    "message": "'results'",
    "stacktrace": "Traceback (most recent call last):\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 56, in run\n    sources = parse_results(payload)\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 42, in parse_…"
   },
   "tool_name": null,
   "model": null,
   "tokens_input": null,
   "tokens_output": null,
   "attempt": 1,
   "metadata": {}
  }
 ],
 "anomalies": [],
 "event_count": 7
}
```

### `GET /executions/{execution_id}/events`

The raw event log in `seq` order, exactly as stored. Paginated.

```bash
curl -s "http://localhost:8000/api/v1/executions/exe_40d8319b2ac749a7aae6c45d29129ead/events?limit=2"
```

`200`

```json
{
 "items": [
  {
   "id": "evt_7d11feb5a67d419babff8c572cc48937",
   "seq": 1,
   "type": "step.started",
   "timestamp": "2026-11-14T20:08:34.830Z",
   "received_at": "2026-11-14T20:38:35.593Z",
   "payload": {
    "name": "plan",
    "input": {
     "question": "How do teams trace what an AI agent did?"
    },
    "model": null,
    "attempt": 1,
    "step_id": "stp_d9d5f7795a20471bab61ebaf56f73017",
    "metadata": {},
    "step_type": "reasoning",
    "tool_name": null,
    "parent_step_id": null
   }
  },
  {
   "id": "evt_e8499d5586704b53a7cbd90abeab8d51",
   "seq": 2,
   "type": "step.completed",
   "timestamp": "2026-11-14T20:08:34.831Z",
   "received_at": "2026-11-14T20:38:35.593Z",
   "payload": {
    "output": {
     "query": "how do teams trace what an ai agent did"
    },
    "step_id": "stp_d9d5f7795a20471bab61ebaf56f73017",
    "metadata": {},
    "tokens_input": null,
    "tokens_output": null
   }
  }
 ],
 "total": 7,
 "limit": 2,
 "offset": 0
}
```

## Stats

Contract §7. A window is a whole number of UTC-aligned buckets ending with the current one: `24h` is this hour
and the 23 before it, `7d` is today and the 6 days before it, `30d` likewise.

### `GET /stats/overview?window=24h|7d|30d`

Default `7d`. Counts executions started inside the window. `success_rate` and `avg_duration_ms` are `null`
when nothing has finished. `total_agents` and `open_anomalies` are current totals, not limited to the window.

```bash
curl -s "http://localhost:8000/api/v1/stats/overview?window=7d"
```

`200`

```json
{
 "window": "7d",
 "total_agents": 3,
 "total_executions": 82,
 "completed": 81,
 "failed": 1,
 "timed_out": 0,
 "running": 0,
 "success_rate": 0.9878048780487805,
 "avg_duration_ms": 906,
 "open_anomalies": 3
}
```

### `GET /stats/timeseries?window=&bucket=hour|day&agent_id=`

One point per bucket, oldest first, with zeros where nothing ran. `bucket` defaults to `hour` for `24h` and
`day` otherwise. With the default bucket the points add up to the overview's totals. Running executions are
counted in the overview but are not in the points.

```bash
curl -s "http://localhost:8000/api/v1/stats/timeseries?window=7d"
```

`200`

```json
{
 "window": "7d",
 "bucket": "day",
 "points": [
  {
   "bucket_start": "2026-11-08T00:00:00.000Z",
   "completed": 3,
   "failed": 0,
   "timed_out": 0,
   "avg_duration_ms": 881
  },
  {
   "bucket_start": "2026-11-09T00:00:00.000Z",
   "completed": 12,
   "failed": 0,
   "timed_out": 0,
   "avg_duration_ms": 820
  },
  "… 5 more"
 ]
}
```

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

```bash
curl -s "http://localhost:8000/api/v1/anomalies?severity=critical&limit=1"
```

`200`

```json
{
 "items": [
  {
   "id": "anm_84a81f36057e47b696b8a5d3b7db9170",
   "type": "ghost_completion",
   "severity": "critical",
   "status": "open",
   "agent_id": "agt_ce1157da711e4712be2c6edfe8272a22",
   "agent_name": "Invoice Processor",
   "execution_id": "exe_e5688ee8a1c54100b1e88ffb804a8498",
   "detected_at": "2026-11-14T20:38:36.265Z",
   "rule_id": "ghost_completion.v1",
   "title": "Reported completed, but submit_invoice never completed",
   "explanation": "The execution reported status completed, but expected 1 step never completed: submit_invoice. Rule fires when a completed execution has a step still running, an expected step (config.expected_steps) with no completed step, or no steps at all.",
   "evidence": [
    {
     "kind": "execution",
     "label": "Expected step submit_invoice never started",
     "ref_id": "exe_e5688ee8a1c54100b1e88ffb804a8498",
     "field": "config.expected_steps",
     "observed": [
      "extract_fields",
      "validate"
     ],
     "expected": [
      "extract_fields",
      "validate",
      "submit_invoice"
     ],
     "excerpt": null
    }
   ]
  }
 ],
 "total": 1,
 "limit": 1,
 "offset": 0
}
```

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

```bash
curl -s "http://localhost:8000/api/v1/investigations/exe_40d8319b2ac749a7aae6c45d29129ead"
```

`200`

```json
{
 "id": "inv_c4bce4bfbbcd4f9f9c1c524f75ce21e0",
 "execution_id": "exe_40d8319b2ac749a7aae6c45d29129ead",
 "status": "completed",
 "trigger": "auto_failure",
 "provider": "rule_based",
 "model": null,
 "created_at": "2026-11-14T20:38:35.609Z",
 "completed_at": "2026-11-14T20:38:35.630Z",
 "error": null,
 "report": {
  "summary": "The execution failed at Step 3 parse_results with KeyError: 'results'. The root cause is confirmed by the deterministic signature missing_key_in_upstream_output.",
  "failing_step_id": "stp_52c2ec9b42604237b472bd57e6ecc406",
  "root_cause": {
   "status": "confirmed",
   "statement": "Step 3 parse_results read the key 'results', which the output of Step 2 web_search (tool web_search) does not contain. That output's keys are: data, meta.",
   "hypothesis_id": "H1",
   "signature": "missing_key_in_upstream_output"
  },
  "facts": [
   {
    "id": "F1",
    "statement": "Execution of research-assistant ended with status failed after 386 ms and 3 steps.",
    "evidence": [
     {
      "kind": "execution",
      "label": "Final status of the execution",
      "ref_id": "exe_40d8319b2ac749a7aae6c45d29129ead",
      "field": "status",
      "observed": "failed",
      "expected": null,
      "excerpt": null
     }
    ]
   },
   {
    "id": "F2",
    "statement": "The execution ended with the error KeyError: 'results'.",
    "evidence": [
     {
      "kind": "execution",
      "label": "Terminal error of the execution",
      "ref_id": "exe_40d8319b2ac749a7aae6c45d29129ead",
      "field": "error.message",
      "observed": "'results'",
      "expected": null,
      "excerpt": "'results'"
     }
    ]
   },
   "… 5 more"
  ],
  "hypotheses": [
   {
    "id": "H1",
    "statement": "Step 3 parse_results read the key 'results', which the output of Step 2 web_search (tool web_search) does not contain. That output's keys are: data, meta.",
    "confidence": "high",
    "reasoning": "Signature missing_key_in_upstream_output: the failing step raised KeyError for 'results' and the nearest preceding tool output has no key 'results'. Both conditions are read directly from the recorded step error and the recorded tool output.",
    "supporting_fact_ids": [
     "F3",
     "F5"
    ],
    "contradicting_fact_ids": []
   }
  ],
  "recommendations": [
   {
    "id": "R1",
    "action": "Make parse_results handle the response shape web_search now returns (keys: data, meta), or pin the response format of web_search.",
    "rationale": "parse_results indexes the key 'results' directly, and the tool's output no longer has it.",
    "hypothesis_id": "H1"
   }
  ],
  "evidence_gaps": [],
  "relevant_step_ids": [
   "stp_2c45922b0984485ea95593c00a2b91e3",
   "stp_52c2ec9b42604237b472bd57e6ecc406"
  ]
 }
}
```

### `POST /investigations/{execution_id}`

Body: `{"force": true}` or nothing. Returns `202` with a queued investigation and runs it in the background.
If one is already queued or running, that one is returned. If a completed one exists, it is returned with
`200` unless `force` is set. `409 conflict` while the execution is still running.

```bash
curl -s -X POST "http://localhost:8000/api/v1/investigations/exe_e5688ee8a1c54100b1e88ffb804a8498"
```

`200`

```json
{
 "id": "inv_e8eac6f5f70d431bbbb4063877e09088",
 "execution_id": "exe_e5688ee8a1c54100b1e88ffb804a8498",
 "status": "completed",
 "trigger": "auto_anomaly",
 "provider": "rule_based",
 "model": null,
 "created_at": "2026-11-14T20:38:36.268Z",
 "completed_at": "2026-11-14T20:38:36.281Z",
 "error": null,
 "report": {
  "summary": "The execution completed. Anomalies raised on it: ghost_completion. The root cause is confirmed by the deterministic signature ghost_completion.",
  "failing_step_id": null,
  "root_cause": {
   "status": "confirmed",
   "statement": "The agent reported the run as completed, but the recorded steps contradict it: Reported completed, but submit_invoice never completed.",
   "hypothesis_id": "H1",
   "signature": "ghost_completion"
  },
  "facts": [
   {
    "id": "F1",
    "statement": "Execution of invoice-processor ended with status completed after 223 ms and 2 steps.",
    "evidence": [
     {
      "kind": "execution",
      "label": "Final status of the execution",
      "ref_id": "exe_e5688ee8a1c54100b1e88ffb804a8498",
      "field": "status",
      "observed": "completed",
      "expected": null,
      "excerpt": null
     }
    ]
   },
   "… 5 more"
  ],
  "hypotheses": [
   {
    "id": "H1",
    "statement": "The agent reported the run as completed, but the recorded steps contradict it: Reported completed, but submit_invoice never completed.",
    "confidence": "high",
    "reasoning": "Signature ghost_completion: the execution's status is completed and the deterministic ghost_completion rule fired (a step still running, an expected step with no completed step, or no steps at all).",
    "supporting_fact_ids": [
     "F5",
     "F4"
    ],
    "contradicting_fact_ids": []
   }
  ],
  "recommendations": [
   {
    "id": "R1",
    "action": "Make the agent fail the run when a required step does not complete, instead of reporting success; check for errors that are caught and ignored before the missing step.",
    "rationale": "The run's reported outcome and its recorded steps disagree, so the reported outcome is not trustworthy.",
    "hypothesis_id": "H1"
   }
  ],
  "evidence_gaps": [],
  "relevant_step_ids": []
 }
}
```

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
