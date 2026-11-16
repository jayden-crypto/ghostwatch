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
| 409 | `conflict` | Investigating or replaying an execution that is still running; claiming a replay that is no longer pending |
| 422 | `validation_error` | `details` is a list of `{loc, msg}`; `loc` is a path such as `["body", "slug"]` |
| 422 | `side_effect_authorization_required` | A `live` replay requested without `authorize_side_effects: true` |
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
 "id": "agt_f6d299400ab940a6bf42d431d9728b6c",
 "name": "Research Assistant",
 "slug": "research-assistant",
 "description": "Answers a question from web search results.",
 "framework": "custom",
 "metadata": {},
 "created_at": "2026-11-15T11:15:55.670Z",
 "stats": {
  "total_executions": 26,
  "completed": 25,
  "failed": 1,
  "timed_out": 0,
  "running": 0,
  "success_rate": 0.9615384615384616,
  "avg_duration_ms": 810,
  "open_anomalies": 0,
  "last_execution": {
   "id": "exe_a1e6a27c39894b4a91f897b6c131e741",
   "agent_id": "agt_f6d299400ab940a6bf42d431d9728b6c",
   "agent_name": "Research Assistant",
   "status": "failed",
   "started_at": "2026-11-15T10:45:55.662Z",
   "ended_at": "2026-11-15T10:45:56.048Z",
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
    "stacktrace": "Traceback (most recent call last):\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 63, in run\n    sources = parse_results(payload)\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 49, in parse_…"
   }
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
   "id": "agt_f53e145acaad4954891dcfa0896aafdc",
   "name": "Invoice Processor",
   "slug": "invoice-processor",
   "description": "Extracts invoice fields, validates them and submits the invoice for payment.",
   "framework": "custom",
   "metadata": {},
   "created_at": "2026-11-15T11:15:56.579Z",
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
     "id": "exe_9a46248f7b724e7bb3cfad6d4b33fbae",
     "agent_id": "agt_f53e145acaad4954891dcfa0896aafdc",
     "agent_name": "Invoice Processor",
     "status": "completed",
     "started_at": "2026-11-15T10:55:55.662Z",
     "ended_at": "2026-11-15T10:55:55.885Z",
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
| `replay_of`, `replay_id` | id | Set by the replay worker. `replay_id` needs `replay_of`, and must be a replay of that execution that this worker has claimed (`409` otherwise) |

`config.expected_steps` lists step names that must complete for the run to count as done (the ghost-completion
rule). `config.timeout_ms` is how long the run may send nothing before it is timed out (default 300000).

```bash
curl -s -X POST "http://localhost:8000/api/v1/executions" \
  -H "Authorization: Bearer $GHOSTWATCH_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"agent_id": "agt_f6d299400ab940a6bf42d431d9728b6c", "input": {"question": "How do teams trace what an AI agent did?"}, "config": {"model": "demo-llm-1", "expected_steps": ["web_search"]}, "tags": ["docs"], "started_at": "2026-11-15T11:16:03.297Z"}'
```

`201`

```json
{
 "id": "exe_d751b452d0b54ac5ac76bc669e417178",
 "agent_id": "agt_f6d299400ab940a6bf42d431d9728b6c",
 "agent_name": "Research Assistant",
 "status": "running",
 "started_at": "2026-11-15T11:16:03.297Z",
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
   "id": "exe_a1e6a27c39894b4a91f897b6c131e741",
   "agent_id": "agt_f6d299400ab940a6bf42d431d9728b6c",
   "agent_name": "Research Assistant",
   "status": "failed",
   "started_at": "2026-11-15T10:45:55.662Z",
   "ended_at": "2026-11-15T10:45:56.048Z",
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
    "stacktrace": "Traceback (most recent call last):\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 63, in run\n    sources = parse_results(payload)\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 49, in parse_…"
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

### Tokens and cost

`tokens_input` and `tokens_output` are the sums over the steps that reported them, and `tokens_total` is their
sum. All three are `null` when no step reported tokens.

`cost_usd` is computed when the execution ends, from each step's own `model` and tokens, using the published
Anthropic list prices in `backend/app/services/pricing.py` (the source and the date they were read are noted
there). It is `null`, never `0` and never a partial sum, when:

- no step reported tokens, or
- any step that reported tokens has a model that is not in the price table, has no model, or reported only
  input or only output.

The figure covers reported input and output tokens at standard prices. Prompt-cache, batch and fast-mode
pricing are not in it, because events do not carry that information. The demo's fake model, `demo-llm-1`, has
no price, so every demo run shows `null`.

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
- A terminal event sets `ended_at`, `duration_ms` (from the client's timestamps, never negative), token
  totals and cost, runs the anomaly rules, and queues an investigation if the run failed, timed out, or raised an
  anomaly of `high` severity or above. Steps still running at that point are left running: that is evidence.

```bash
curl -s -X POST "http://localhost:8000/api/v1/executions/exe_d751b452d0b54ac5ac76bc669e417178/events" \
  -H "Authorization: Bearer $GHOSTWATCH_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"events": [{"seq": 1, "type": "step.started", "timestamp": "2026-11-15T11:16:03.307Z", "payload": {"step_id": "stp_e8ba6d742b8340fc8faae6aeabc8d96d", "name": "web_search", "step_type": "tool_call", "tool_name": "web_search", "input": {"query": "agent tracing"}}}, {"seq": 2, "type": "step.completed", "timestamp": "2026-11-15T11:16:03.677Z", "payload": {"step_id": "stp_e8ba6d742b8340fc8faae6aeabc8d96d", "output": {"results": [], "total": 0}}}, {"seq": 3, "type": "execution.completed", "timestamp": "2026-11-15T11:16:03.697Z", "payload": {"output": {"answer": "…"}}}]}'
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
curl -s -X POST "http://localhost:8000/api/v1/executions/exe_d751b452d0b54ac5ac76bc669e417178/events" \
  -H "Authorization: Bearer $GHOSTWATCH_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"events": [{"seq": 1, "type": "step.started", "timestamp": "2026-11-15T11:16:03.307Z", "payload": {"step_id": "stp_e8ba6d742b8340fc8faae6aeabc8d96d", "name": "web_search", "step_type": "tool_call", "tool_name": "web_search", "input": {"query": "agent tracing"}}}, {"seq": 2, "type": "step.completed", "timestamp": "2026-11-15T11:16:03.677Z", "payload": {"step_id": "stp_e8ba6d742b8340fc8faae6aeabc8d96d", "output": {"results": [], "total": 0}}}, {"seq": 3, "type": "execution.completed", "timestamp": "2026-11-15T11:16:03.697Z", "payload": {"output": {"answer": "…"}}}]}'
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
curl -s -X POST "http://localhost:8000/api/v1/executions/exe_d751b452d0b54ac5ac76bc669e417178/events" \
  -H "Authorization: Bearer $GHOSTWATCH_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"events": [{"seq": 4, "type": "step.started", "timestamp": "2026-11-15T11:16:04.197Z", "payload": {"step_id": "stp_3dc5c11c428c49f5b188bb32499fb1b0", "name": "late", "step_type": "custom"}}]}'
```

`409`

```json
{
 "error": {
  "code": "execution_already_terminal",
  "message": "Execution exe_d751b452d0b54ac5ac76bc669e417178 is already completed; only log events are accepted.",
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
computed by the backend. A step whose parent is not in the execution is laid out as a root. Every step of a
replay's execution has `metadata.replay_source` (see Replays).

This is the schema-change failure from the demo: `web_search` returned `data` and `meta`, and
`parse_results` asked for `results`.

```bash
curl -s "http://localhost:8000/api/v1/executions/exe_a1e6a27c39894b4a91f897b6c131e741/trace"
```

`200`

```json
{
 "execution": {
  "id": "exe_a1e6a27c39894b4a91f897b6c131e741",
  "agent_id": "agt_f6d299400ab940a6bf42d431d9728b6c",
  "agent_name": "Research Assistant",
  "status": "failed",
  "started_at": "2026-11-15T10:45:55.662Z",
  "ended_at": "2026-11-15T10:45:56.048Z",
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
   "stacktrace": "Traceback (most recent call last):\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 63, in run\n    sources = parse_results(payload)\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 49, in parse_…"
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
  "replay_ids": [
   "rpl_954ff24367b540b1b34b61dd688a0123"
  ]
 },
 "steps": [
  {
   "id": "stp_e2021e113daf4b5cbf7ba05c7e460f4c",
   "execution_id": "exe_a1e6a27c39894b4a91f897b6c131e741",
   "parent_step_id": null,
   "ordinal": 1,
   "depth": 0,
   "name": "plan",
   "type": "reasoning",
   "status": "completed",
   "started_at": "2026-11-15T10:45:55.663Z",
   "ended_at": "2026-11-15T10:45:55.664Z",
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
   "id": "stp_c733bd2a2b344f7bb61084f31a88de5f",
   "execution_id": "exe_a1e6a27c39894b4a91f897b6c131e741",
   "parent_step_id": null,
   "ordinal": 2,
   "depth": 0,
   "name": "web_search",
   "type": "tool_call",
   "status": "completed",
   "started_at": "2026-11-15T10:45:55.665Z",
   "ended_at": "2026-11-15T10:45:56.045Z",
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
   "id": "stp_91f5f3f5e84d446bbbe1b2f06cffa577",
   "execution_id": "exe_a1e6a27c39894b4a91f897b6c131e741",
   "parent_step_id": null,
   "ordinal": 3,
   "depth": 0,
   "name": "parse_results",
   "type": "reasoning",
   "status": "failed",
   "started_at": "2026-11-15T10:45:56.046Z",
   "ended_at": "2026-11-15T10:45:56.047Z",
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
    "stacktrace": "Traceback (most recent call last):\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 63, in run\n    sources = parse_results(payload)\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 49, in parse_…"
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
curl -s "http://localhost:8000/api/v1/executions/exe_a1e6a27c39894b4a91f897b6c131e741/events?limit=2"
```

`200`

```json
{
 "items": [
  {
   "id": "evt_feebf5eb720545cf90385e08faec5967",
   "seq": 1,
   "type": "step.started",
   "timestamp": "2026-11-15T10:45:55.663Z",
   "received_at": "2026-11-15T11:15:56.547Z",
   "payload": {
    "name": "plan",
    "input": {
     "question": "How do teams trace what an AI agent did?"
    },
    "model": null,
    "attempt": 1,
    "step_id": "stp_e2021e113daf4b5cbf7ba05c7e460f4c",
    "metadata": {},
    "step_type": "reasoning",
    "tool_name": null,
    "parent_step_id": null
   }
  },
  {
   "id": "evt_608373f2220a49a4bef27129043d17be",
   "seq": 2,
   "type": "step.completed",
   "timestamp": "2026-11-15T10:45:55.664Z",
   "received_at": "2026-11-15T11:15:56.547Z",
   "payload": {
    "output": {
     "query": "how do teams trace what an ai agent did"
    },
    "step_id": "stp_e2021e113daf4b5cbf7ba05c7e460f4c",
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
 "total_executions": 81,
 "completed": 80,
 "failed": 1,
 "timed_out": 0,
 "running": 0,
 "success_rate": 0.9876543209876543,
 "avg_duration_ms": 914,
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
   "bucket_start": "2026-11-09T00:00:00.000Z",
   "completed": 9,
   "failed": 0,
   "timed_out": 0,
   "avg_duration_ms": 870
  },
  {
   "bucket_start": "2026-11-10T00:00:00.000Z",
   "completed": 12,
   "failed": 0,
   "timed_out": 0,
   "avg_duration_ms": 828
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
   "id": "anm_fab9f1bfc8bf4601bfe9fac08276cfbc",
   "type": "ghost_completion",
   "severity": "critical",
   "status": "open",
   "agent_id": "agt_f53e145acaad4954891dcfa0896aafdc",
   "agent_name": "Invoice Processor",
   "execution_id": "exe_9a46248f7b724e7bb3cfad6d4b33fbae",
   "detected_at": "2026-11-15T11:15:57.448Z",
   "rule_id": "ghost_completion.v1",
   "title": "Reported completed, but submit_invoice never completed",
   "explanation": "The execution reported status completed, but expected 1 step never completed: submit_invoice. Rule fires when a completed execution has a step still running, an expected step (config.expected_steps) with no completed step, or no steps at all.",
   "evidence": [
    {
     "kind": "execution",
     "label": "Expected step submit_invoice never started",
     "ref_id": "exe_9a46248f7b724e7bb3cfad6d4b33fbae",
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

### `PATCH /anomalies/{anomaly_id}`

Body: `{"status": "open" | "acknowledged" | "resolved"}`. Returns the anomaly. Only the status can be changed,
and any status may follow any other, so a resolved anomaly can be reopened. Only `open` anomalies count
towards `open_anomalies` and towards an agent's `health`.

```bash
curl -s -X PATCH "http://localhost:8000/api/v1/anomalies/anm_9b7a2ee16f194c3d9817ddbfb6bd6e14" \
  -H 'Content-Type: application/json' \
  -d '{"status": "acknowledged"}'
```

`200`

```json
{
 "id": "anm_9b7a2ee16f194c3d9817ddbfb6bd6e14",
 "type": "excessive_retries",
 "severity": "medium",
 "status": "acknowledged",
 "agent_id": "agt_03c1773cfa0c45eb97a6c3bf4debfa87",
 "agent_name": "Support Triage",
 "execution_id": "exe_316d93f94cad476b9e1ba097fa97fbd7",
 "detected_at": "2026-11-15T11:15:58.238Z",
 "rule_id": "excessive_retries.v1",
 "title": "2 retried steps, highest attempt 3",
 "explanation": "The highest attempt number in this execution is 3 and the sum of (attempt - 1) over all steps is 3. Rule fires when any step has attempt >= 3 or the sum is >= 5.",
 "evidence": [
  {
   "kind": "step",
   "label": "Step 4 retrieve_kb (attempt 3) is a retry",
   "ref_id": "stp_8530996309044783856d79485841d8ff",
   "field": "attempt",
   "observed": 3,
   "expected": "below 3",
   "excerpt": null
  },
  "… 1 more"
 ]
}
```

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

`rule_based` is the default and needs no key. `fable` is optional: it needs `ANTHROPIC_API_KEY`, and each
investigation is a paid API call. Every example in this document was produced with `rule_based`.

Investigations start automatically when an execution fails or times out (`auto_failure`), or raises an anomaly
of `high` severity or above (`auto_anomaly`).

### `GET /investigations/{execution_id}`

The latest investigation of the execution, or `404`. `report` is `null` until `status` is `completed`.
Poll every 2 s while `status` is `queued` or `running`.

```bash
curl -s "http://localhost:8000/api/v1/investigations/exe_a1e6a27c39894b4a91f897b6c131e741"
```

`200`

```json
{
 "id": "inv_4252727d000b4ba59212db04ffb747b0",
 "execution_id": "exe_a1e6a27c39894b4a91f897b6c131e741",
 "status": "completed",
 "trigger": "auto_failure",
 "provider": "rule_based",
 "model": null,
 "created_at": "2026-11-15T11:15:56.564Z",
 "completed_at": "2026-11-15T11:15:56.591Z",
 "error": null,
 "report": {
  "summary": "The execution failed at Step 3 parse_results with KeyError: 'results'. The root cause is confirmed by the deterministic signature missing_key_in_upstream_output.",
  "failing_step_id": "stp_91f5f3f5e84d446bbbe1b2f06cffa577",
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
      "ref_id": "exe_a1e6a27c39894b4a91f897b6c131e741",
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
      "ref_id": "exe_a1e6a27c39894b4a91f897b6c131e741",
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
   "stp_c733bd2a2b344f7bb61084f31a88de5f",
   "stp_91f5f3f5e84d446bbbe1b2f06cffa577"
  ]
 }
}
```

### `POST /investigations/{execution_id}`

Body: `{"force": true}` or nothing. Returns `202` with a queued investigation and runs it in the background.
If one is already queued or running, that one is returned. If a completed one exists, it is returned with
`200` unless `force` is set. `409 conflict` while the execution is still running.

```bash
curl -s -X POST "http://localhost:8000/api/v1/investigations/exe_9a46248f7b724e7bb3cfad6d4b33fbae"
```

`200`

```json
{
 "id": "inv_2d8ee14e1ea44b9fa5131a02953bd844",
 "execution_id": "exe_9a46248f7b724e7bb3cfad6d4b33fbae",
 "status": "completed",
 "trigger": "auto_anomaly",
 "provider": "rule_based",
 "model": null,
 "created_at": "2026-11-15T11:15:57.451Z",
 "completed_at": "2026-11-15T11:15:57.465Z",
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
      "ref_id": "exe_9a46248f7b724e7bb3cfad6d4b33fbae",
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

## Replays

Contract §10. The backend never runs agent code. A replay is a request that a **replay worker** picks up: a
process that has the agent's code and the SDK (`ghostwatch.ReplayWorker`; for the demo,
`cd demo && uv run python replay.py worker`). The worker runs the agent again with the original input, as a
new execution linked to the original. Until a worker is running, a replay stays `pending`.

What runs during a replay depends on `mode`:

- **`sandbox`** (the default choice): no tool with side effects ever runs.
  - A tool or model call the original execution made returns its recorded output, or raises its recorded
    error. The function is not called.
  - A call the original never made runs for real only if it is a model call or a tool declared
    `side_effects=False`. Any other tool is blocked: its step fails with error type
    `SandboxRecordingMissing`. A tool that does not declare `side_effects` counts as having them.
- **`live`**: every tool runs for real. It is refused unless the request says `authorize_side_effects: true`.

Every step of a replay's execution carries `metadata.replay_source`:

| `replay_source` | Meaning |
|---|---|
| `recorded` | Served from the original run's recording; nothing was called |
| `executed` | Ran for real in this replay |
| `blocked` | Not recorded and not safe to run in a sandbox; the step failed without calling the tool |

### `POST /executions/{execution_id}/replay`

| Body field | Type | Notes |
|---|---|---|
| `mode` | `sandbox` or `live` | Required |
| `authorize_side_effects` | boolean | Required to be the JSON value `true` for `live`; ignored for `sandbox` |
| `note` | string or null | Optional, shown with the replay |

Returns `201` with the replay in status `pending`. `409 conflict` while the execution is still running.

```bash
curl -s -X POST "http://localhost:8000/api/v1/executions/exe_a1e6a27c39894b4a91f897b6c131e741/replay" \
  -H 'Content-Type: application/json' \
  -d '{"mode": "sandbox", "note": "After the parse_results fix"}'
```

`201`

```json
{
 "id": "rpl_954ff24367b540b1b34b61dd688a0123",
 "original_execution_id": "exe_a1e6a27c39894b4a91f897b6c131e741",
 "replay_execution_id": null,
 "mode": "sandbox",
 "status": "pending",
 "side_effects_authorized": false,
 "note": "After the parse_results fix",
 "requested_at": "2026-11-15T11:16:05.320Z",
 "claimed_at": null,
 "completed_at": null,
 "error": null,
 "comparison": null
}
```

A `live` replay without authorization:

```bash
curl -s -X POST "http://localhost:8000/api/v1/executions/exe_a1e6a27c39894b4a91f897b6c131e741/replay" \
  -H 'Content-Type: application/json' \
  -d '{"mode": "live"}'
```

`422`

```json
{
 "error": {
  "code": "side_effect_authorization_required",
  "message": "A live replay runs the agent's tools for real. Set authorize_side_effects to true to confirm, or use mode sandbox.",
  "details": null
 }
}
```

### `GET /replays/{replay_id}`

Poll every 2 s while `status` is `pending` or `claimed`. `comparison` is `null` until the replay's execution
has ended. A replay whose agent fails again is still `completed`: `outcome` says how the two runs compare.

| `outcome` | Original | Replay |
|---|---|---|
| `fixed` | failed | completed |
| `same_failure` | failed | failed at a step with the same name, with the same error type |
| `different_failure` | failed | failed at another step, or with another error type |
| `regressed` | completed | failed |
| `both_succeeded` | completed | completed |
| `inconclusive` | either run timed out or has not finished | |

`step_diffs` aligns the two runs by step `ordinal` and name. `change` is `unchanged`, `status_changed`,
`output_changed`, `added` (only in the replay) or `removed` (only in the original). `replay_source` repeats the
replay step's `metadata.replay_source`, and is `null` for a `removed` step.

This is the schema-change failure replayed in the sandbox after the parser was fixed: `web_search` was served
from the recording, and `summarize`, which the original run never reached, ran for real.

```bash
curl -s "http://localhost:8000/api/v1/replays/rpl_954ff24367b540b1b34b61dd688a0123"
```

`200`

```json
{
 "id": "rpl_954ff24367b540b1b34b61dd688a0123",
 "original_execution_id": "exe_a1e6a27c39894b4a91f897b6c131e741",
 "replay_execution_id": "exe_a7c1e40d45724dd79ec22b3d9b77db00",
 "mode": "sandbox",
 "status": "completed",
 "side_effects_authorized": false,
 "note": "After the parse_results fix",
 "requested_at": "2026-11-15T11:16:05.320Z",
 "claimed_at": "2026-11-15T11:16:05.903Z",
 "completed_at": "2026-11-15T11:16:06.554Z",
 "error": null,
 "comparison": {
  "original": {
   "id": "exe_a1e6a27c39894b4a91f897b6c131e741",
   "agent_id": "agt_f6d299400ab940a6bf42d431d9728b6c",
   "agent_name": "Research Assistant",
   "status": "failed",
   "started_at": "2026-11-15T10:45:55.662Z",
   "ended_at": "2026-11-15T10:45:56.048Z",
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
    "stacktrace": "Traceback (most recent call last):\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 63, in run\n    sources = parse_results(payload)\n  File \"/Users/jayden/Desktop/ghostwatch/demo/agents/research_assistant.py\", line 49, in parse_…"
   }
  },
  "replay": {
   "id": "exe_a7c1e40d45724dd79ec22b3d9b77db00",
   "agent_id": "agt_f6d299400ab940a6bf42d431d9728b6c",
   "agent_name": "Research Assistant",
   "status": "completed",
   "started_at": "2026-11-15T11:16:05.923Z",
   "ended_at": "2026-11-15T11:16:06.425Z",
   "duration_ms": 502,
   "step_count": 4,
   "tokens_total": 199,
   "cost_usd": null,
   "anomaly_count": 0,
   "has_investigation": false,
   "replay_of": "exe_a1e6a27c39894b4a91f897b6c131e741",
   "error": null
  },
  "outcome": "fixed",
  "duration_delta_ms": 116,
  "tokens_delta": null,
  "step_count_delta": 1,
  "step_diffs": [
   {
    "ordinal": 1,
    "name": "plan",
    "original_step_id": "stp_e2021e113daf4b5cbf7ba05c7e460f4c",
    "replay_step_id": "stp_5bc0369815a14412a8fb369a6749b0af",
    "change": "unchanged",
    "original_status": "completed",
    "replay_status": "completed",
    "replay_source": "executed"
   },
   {
    "ordinal": 2,
    "name": "web_search",
    "original_step_id": "stp_c733bd2a2b344f7bb61084f31a88de5f",
    "replay_step_id": "stp_88ff38ae1ef1451896870dff19fb21d5",
    "change": "unchanged",
    "original_status": "completed",
    "replay_status": "completed",
    "replay_source": "recorded"
   },
   {
    "ordinal": 3,
    "name": "parse_results",
    "original_step_id": "stp_91f5f3f5e84d446bbbe1b2f06cffa577",
    "replay_step_id": "stp_b88535a7fa8e46c58ca93b6e8183301c",
    "change": "status_changed",
    "original_status": "failed",
    "replay_status": "completed",
    "replay_source": "executed"
   },
   {
    "ordinal": 4,
    "name": "summarize",
    "original_step_id": null,
    "replay_step_id": "stp_2b1bb5ede205436c8396d906c012c4a2",
    "change": "added",
    "original_status": null,
    "replay_status": "completed",
    "replay_source": "executed"
   }
  ]
 }
}
```

### `GET /replays`

| Query | Notes |
|---|---|
| `original_execution_id` | Replays of this execution |
| `status` | Comma-separated: `pending`, `claimed`, `completed`, `failed` |
| `sort` | `requested_at` (default `-requested_at`) |
| `limit`, `offset` | Pagination |

### `POST /replays/{replay_id}/claim` 🔑

For replay workers. Gives a `pending` replay to exactly one worker: the first claim wins and any later one is
a `409 conflict`. The response is `{replay, bundle}`. `bundle.original_execution` is the execution being
replayed, and `bundle.recorded_calls` lists its tool and model calls in order, each with `step_name`,
`step_type`, `tool_name`, `occurrence` (1 for the first call of that tool or step name, 2 for the second, and
so on), `input`, `output` and `error`. The worker then starts an execution with `replay_of` and `replay_id` set
and sends its events as usual; when that execution ends, the replay becomes `completed`.

## Not implemented

Nothing: every endpoint in the contract is implemented.
