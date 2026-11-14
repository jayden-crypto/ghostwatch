# Ghostwatch API Contract — v1.1

**Status:** FROZEN for implementation. Changes only via the contract-change process in `CONTRIBUTING.md` (a PR touching only `contract/`, approved by both Jayden and Adit).

This file is the single source of truth for every byte that crosses the frontend/backend boundary. The backend (Jayden) implements it. The frontend (Adit) consumes it, first through mocks and then live. If code and this file disagree, the code is wrong.

---

## 0. Global conventions

| Concern | Rule |
|---|---|
| Base URL | `http://localhost:8000/api/v1` |
| JSON key casing | `snake_case` everywhere, both directions. The frontend does **not** convert to camelCase. |
| IDs | Prefixed opaque strings: `agt_`, `exe_`, `stp_`, `evt_`, `anm_`, `inv_`, `rpl_` followed by 32 lowercase hex chars (uuid4 hex). Example: `exe_3f9c2a7e1b4d4e0f9a8b7c6d5e4f3a2b`. Treat as opaque; never parse. |
| Timestamps | ISO 8601, UTC, millisecond precision, `Z` suffix: `"2026-11-14T10:32:05.123Z"`. Never local time, never epoch numbers. |
| Durations | Integer milliseconds, field names end in `_ms`. |
| Money | `cost_usd: number \| null`. `null` means "unknown" (no usage data or no pricing for that model). Never `0` as a stand-in for unknown. |
| Tokens | `integer \| null`. `null` = not reported. |
| Arbitrary payloads | Typed as `Json` (any JSON value). Any single payload field larger than 64 KB is stored truncated as `{"_truncated": true, "original_bytes": <int>, "preview": "<first 2000 chars>"}`. The frontend must render this marker explicitly ("Payload truncated — 182 KB"). |
| Nullability | Every field listed is always present in responses. Optional-ness is expressed as `null`, never by omitting the key. |
| Pagination | List endpoints take `limit` (default 50, max 200) and `offset` (default 0) and return `Page<T>`. |
| Sorting | `sort` query param, field name with optional `-` prefix for descending. Default per endpoint is stated below. |
| Auth (MVP) | Ingestion endpoints (marked 🔑) require `Authorization: Bearer <GHOSTWATCH_API_KEY>`. Dashboard endpoints are unauthenticated on localhost. This is a known MVP limitation and is documented in the README. |
| CORS | Backend allows origin `http://localhost:3000`. |

### Error format (every non-2xx response)

```json
{
  "error": {
    "code": "not_found",
    "message": "Execution exe_3f9c... does not exist.",
    "details": null
  }
}
```

| HTTP | `code` values |
|---|---|
| 400 | `bad_request` |
| 401 | `unauthorized` |
| 404 | `not_found` |
| 409 | `conflict`, `execution_already_terminal` |
| 422 | `validation_error` (`details` = list of `{loc, msg}`), `side_effect_authorization_required` |
| 500 | `internal_error` (never leak stack traces) |
| 503 | `llm_unavailable` (only from investigation endpoints, and only when the rule-based fallback is disabled) |

FastAPI's default 422 body must be overridden to match this shape.

---

## 1. Enums (exact string values)

```ts
type ExecutionStatus   = "running" | "completed" | "failed" | "timed_out";
type StepStatus        = "running" | "completed" | "failed";
type StepType          = "input" | "llm_call" | "tool_call" | "retrieval" | "reasoning" | "output" | "custom";
type Severity          = "low" | "medium" | "high" | "critical";
type AnomalyType       = "duration_spike" | "token_spike" | "repeated_tool_failure" | "excessive_retries"
                       | "repeated_timeouts" | "ghost_completion" | "stale_execution" | "unexpected_pattern";
type AnomalyStatus     = "open" | "acknowledged" | "resolved";
type AgentHealth       = "healthy" | "degraded" | "failing" | "idle";
type InvestigationStatus  = "queued" | "running" | "completed" | "failed";
type InvestigationTrigger = "manual" | "auto_failure" | "auto_anomaly";
type InvestigationProvider = "fable" | "rule_based";
type Confidence        = "low" | "medium" | "high";
type RootCauseStatus   = "confirmed" | "probable" | "insufficient_evidence";
type EvidenceKind      = "step" | "event" | "metric" | "baseline" | "execution" | "anomaly";
type ReplayMode        = "sandbox" | "live";
type ReplayStatus      = "pending" | "claimed" | "completed" | "failed";
type ReplayOutcome     = "same_failure" | "different_failure" | "fixed" | "regressed" | "both_succeeded" | "inconclusive";
type StepChange        = "unchanged" | "status_changed" | "output_changed" | "added" | "removed";
type EventType         = "step.started" | "step.completed" | "step.failed"
                       | "execution.completed" | "execution.failed" | "execution.timed_out" | "log";
```

The frontend must handle every value in every enum (a badge, label and colour for each). No "other" fallbacks hiding unknown values. Log them to the console instead.

---

## 2. Shared types

```ts
type ID = string;
type Timestamp = string;
type Json = null | boolean | number | string | Json[] | { [k: string]: Json };

interface Page<T> { items: T[]; total: number; limit: number; offset: number; }

interface ErrorInfo {
  type: string;              // e.g. "KeyError", "HTTPError", "TimeoutError"
  message: string;
  stacktrace: string | null;
}

interface Evidence {
  kind: EvidenceKind;
  label: string;             // human-readable, e.g. "Tool output of web_search (attempt 1)"
  ref_id: ID | null;         // the step/event/execution/anomaly this points at; null for metric/baseline
  field: string | null;      // dotted path inside the referenced object, e.g. "output.data" or "error.message"
  observed: Json;            // what was actually seen
  expected: Json;            // threshold, baseline value or expected shape; null if not applicable
  excerpt: string | null;    // short verbatim excerpt (≤ 500 chars) copied from stored data, never paraphrased
}
```

**Evidence invariant:** `observed` and `excerpt` must be copied from stored data by backend code. They are never generated by an LLM. The frontend renders every `ref_id` that points at a step as a link that opens that step in the trace explorer.

---

## 3. Agents

```ts
interface AgentStats {
  total_executions: number;
  completed: number;
  failed: number;
  timed_out: number;
  running: number;
  success_rate: number | null;     // completed / (completed+failed+timed_out), 0..1; null if denominator is 0
  avg_duration_ms: number | null;  // over terminal executions
  open_anomalies: number;
  last_execution: ExecutionSummary | null;
  health: AgentHealth;
}

interface Agent {
  id: ID;
  name: string;              // "Research Assistant"
  slug: string;              // "research-assistant", unique, [a-z0-9-]+
  description: string | null;
  framework: string | null;  // "custom", "langgraph", ...
  metadata: { [k: string]: Json };
  created_at: Timestamp;
  stats: AgentStats;
}
```

**Health rule** (computed by the backend over the agent's last 20 terminal executions):
- `idle`: zero executions ever.
- `failing`: success_rate < 0.5 **or** any open `critical` anomaly.
- `degraded`: success_rate < 0.9 **or** any open `high` anomaly.
- `healthy`: otherwise.

| Method | Path | Body | Response |
|---|---|---|---|
| POST 🔑 | `/agents` | `{name, slug, description?, framework?, metadata?}` | `201 Agent` if created, `200 Agent` if the slug already exists (idempotent upsert; updates name/description/framework/metadata) |
| GET | `/agents` | — | `Page<Agent>`, default sort `name`. Query: `q` (name/slug contains), `health` |
| GET | `/agents/{agent_id}` | — | `Agent` |

---

## 4. Executions

```ts
interface ExecutionSummary {
  id: ID;
  agent_id: ID;
  agent_name: string;
  status: ExecutionStatus;
  started_at: Timestamp;
  ended_at: Timestamp | null;
  duration_ms: number | null;      // null while running
  step_count: number;
  tokens_total: number | null;
  cost_usd: number | null;
  anomaly_count: number;
  has_investigation: boolean;
  replay_of: ID | null;            // original execution id if this is a replay
  error: ErrorInfo | null;         // terminal error if failed / timed_out
}

interface ExecutionDetail extends ExecutionSummary {
  input: Json;
  output: Json;
  config: ExecutionConfig;
  tokens_input: number | null;
  tokens_output: number | null;
  tags: string[];
  replay_ids: ID[];                // replays created from this execution
}

interface ExecutionConfig {
  model: string | null;            // e.g. "claude-fable-5-2"
  params: { [k: string]: Json };   // temperature etc.
  expected_steps: string[] | null; // step names that must appear for a run to count as truly complete (ghost_completion rule)
  timeout_ms: number | null;       // stale_execution rule; default 300000 if null
  [k: string]: Json;               // free-form extras allowed
}
```

| Method | Path | Body | Response |
|---|---|---|---|
| POST 🔑 | `/executions` | `{agent_id, input, config, tags?, started_at?, replay_of?, replay_id?}` | `201 ExecutionDetail` with `status: "running"` |
| GET | `/executions` | — | `Page<ExecutionSummary>` |
| GET | `/executions/{execution_id}` | — | `ExecutionDetail` |

`GET /executions` query params (all optional, combinable):
`agent_id`, `status` (comma-separated list), `started_after`, `started_before` (Timestamps), `min_duration_ms`, `max_duration_ms`, `has_anomaly` (`true|false`), `is_replay` (`true|false`), `replay_of` (ID), `q` (matches execution id prefix or agent name), `sort` (default `-started_at`; allowed `started_at`, `duration_ms`, `tokens_total`, `cost_usd`, each with optional `-`), `limit`, `offset`.

---

## 5. Event ingestion (the only way execution state changes)

Executions are event-sourced. The raw `events` table is append-only and is the evidentiary record. Steps and execution status are derived from events by the backend.

```ts
interface IngestEvent {
  seq: number;              // client-assigned, starts at 1, strictly increasing per execution. (execution_id, seq) is unique → duplicates are ignored, which makes retries safe.
  type: EventType;
  timestamp: Timestamp;     // client wall-clock time of the event
  payload: EventPayload;    // shape depends on type, see below
}
```

| `type` | `payload` |
|---|---|
| `step.started` | `{step_id: ID, parent_step_id: ID \| null, name: string, step_type: StepType, input: Json, tool_name: string \| null, model: string \| null, attempt: number (1-based, default 1), metadata: {...}}`. `step_id` is generated client-side by the SDK (`stp_` + uuid4 hex). |
| `step.completed` | `{step_id, output: Json, tokens_input: number \| null, tokens_output: number \| null, metadata: {...}}` |
| `step.failed` | `{step_id, error: ErrorInfo, output: Json}` |
| `execution.completed` | `{output: Json}` |
| `execution.failed` | `{error: ErrorInfo}` |
| `execution.timed_out` | `{}` |
| `log` | `{level: "debug"\|"info"\|"warning"\|"error", message: string, step_id: ID \| null}` |

| Method | Path | Body | Response |
|---|---|---|---|
| POST 🔑 | `/executions/{execution_id}/events` | `{events: IngestEvent[]}` (1–500) | `202 {accepted: number, duplicates: number, execution_status: ExecutionStatus}` |

Processing rules:
1. Events in a batch are processed in `seq` order inside one DB transaction.
2. Duplicate `(execution_id, seq)` is counted in `duplicates` and skipped, not an error.
3. After a terminal `execution.*` event, further non-`log` events are rejected with `409 execution_already_terminal` for the whole batch.
4. A `step.completed`/`step.failed` for an unknown `step_id` gets `422 validation_error`.
5. On a terminal event, the backend synchronously: computes `ended_at`, `duration_ms`, token totals and cost, then runs the anomaly engine for that execution. If status is `failed` or `timed_out`, or any anomaly ≥ `high` was raised, it queues an investigation with trigger `auto_failure` / `auto_anomaly`.
6. Execution token totals = sum of step tokens (null if no step reported tokens).

---

## 6. Traces

```ts
interface Step {
  id: ID;
  execution_id: ID;
  parent_step_id: ID | null;
  ordinal: number;          // 1-based order of step.started events within the execution
  depth: number;            // 0 for root steps; computed by backend from parent chain
  name: string;
  type: StepType;
  status: StepStatus;
  started_at: Timestamp;
  ended_at: Timestamp | null;
  duration_ms: number | null;
  offset_ms: number;        // started_at minus execution.started_at; for waterfall layout
  input: Json;
  output: Json;
  error: ErrorInfo | null;
  tool_name: string | null;
  model: string | null;
  tokens_input: number | null;
  tokens_output: number | null;
  attempt: number;
  metadata: { [k: string]: Json };
}

interface Trace {
  execution: ExecutionDetail;
  steps: Step[];            // sorted by ordinal; flat list, frontend builds the tree from parent_step_id
  anomalies: Anomaly[];     // anomalies attached to this execution
  event_count: number;
}
```

| Method | Path | Response |
|---|---|---|
| GET | `/executions/{execution_id}/trace` | `Trace` |
| GET | `/executions/{execution_id}/events` | `Page<{id, seq, type, timestamp, received_at, payload}>` sorted by `seq` (raw evidence view) |

---

## 7. Stats

| Method | Path | Response |
|---|---|---|
| GET | `/stats/overview?window=24h\|7d\|30d` (default `7d`) | `{window, total_agents, total_executions, completed, failed, timed_out, running, success_rate: number\|null, avg_duration_ms: number\|null, open_anomalies}` |
| GET | `/stats/timeseries?window=24h\|7d\|30d&bucket=hour\|day&agent_id=` | `{window, bucket, points: [{bucket_start: Timestamp, completed, failed, timed_out, avg_duration_ms: number\|null}]}`. Empty buckets are included with zeros, so charts never have gaps. |

---

## 8. Anomalies

```ts
interface Anomaly {
  id: ID;
  type: AnomalyType;
  severity: Severity;
  status: AnomalyStatus;
  agent_id: ID;
  agent_name: string;
  execution_id: ID | null;   // for agent-level anomalies such as repeated_timeouts: the most recent related execution; null only if none exists
  detected_at: Timestamp;
  rule_id: string;           // e.g. "duration_spike.v1"
  title: string;             // ≤ 80 chars: "Duration 4.2× above baseline"
  explanation: string;       // deterministic template text explaining why the rule fired, including the threshold
  evidence: Evidence[];      // ≥ 1 item, always
}
```

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/anomalies` | — | `Page<Anomaly>`, default sort `-detected_at`. Query: `agent_id`, `execution_id`, `type`, `severity` (comma list), `status` (comma list) |
| GET | `/anomalies/{anomaly_id}` | — | `Anomaly` |
| PATCH | `/anomalies/{anomaly_id}` | `{status: AnomalyStatus}` | `Anomaly` (P1) |

**Rules (v1, deterministic).** "Baseline" means the agent's last 20 **completed** executions, excluding the one being evaluated and excluding replays. Any rule that needs a baseline is skipped when there are fewer than 5 baseline runs (the backend logs the skip). Thresholds live in one backend config module so they are easy to show and tune.

| `type` | Fires when | Severity |
|---|---|---|
| `duration_spike` | `duration_ms > max(3 × baseline_median, 1.5 × baseline_p95)` | medium; high if > 5× median |
| `token_spike` | `tokens_total > max(2 × baseline_median, baseline_p95)` | medium; high if > 4× median |
| `repeated_tool_failure` | same `tool_name` has ≥ 3 failed steps in one execution, **or** the agent's last 3 executions all failed on a step with the same `tool_name` | high |
| `excessive_retries` | any step has `attempt ≥ 3`, or the sum of `(attempt - 1)` over the execution is ≥ 5 | medium |
| `repeated_timeouts` | ≥ 3 of the agent's last 10 executions are `timed_out` (agent-level, `execution_id` = most recent one) | high |
| `ghost_completion` | status is `completed` **and** any of: a step is still `running`; `config.expected_steps` contains a name with no `completed` step; zero steps recorded | **critical** (Ghostwatch's signature detection: the agent says it finished but the evidence says it didn't) |
| `stale_execution` | status `running` with no event received for `config.timeout_ms` (default 300000). The backend sweeper marks it `timed_out` and records this anomaly. | high |
| `unexpected_pattern` | the execution's step-type signature (ordered list of `type:name`) contains a `tool_name` never seen in the baseline, **or** `step_count > 2 × baseline max step_count` | low |

`explanation` example (template-generated, never LLM): `"Execution took 41,250 ms. Baseline median for research-assistant is 9,800 ms over 20 runs (p95 12,400 ms). Rule fires above max(3× median, 1.5× p95) = 29,400 ms."`

---

## 9. Investigations

The core intelligence feature. **Facts are computed by deterministic backend code. Hypotheses are proposed by the LLM, or by the rule-based fallback, and must cite facts.** The UI renders these as visually distinct sections.

```ts
interface Fact {
  id: string;                 // "F1", "F2", ... unique within a report
  statement: string;          // template-generated from stored data
  evidence: Evidence[];       // ≥ 1
}

interface Hypothesis {
  id: string;                 // "H1", ...
  statement: string;
  confidence: Confidence;
  reasoning: string;          // why the cited facts support this
  supporting_fact_ids: string[];    // ≥ 1, each must exist in facts
  contradicting_fact_ids: string[];
}

interface Recommendation {
  id: string;                 // "R1", ...
  action: string;
  rationale: string;
  hypothesis_id: string | null;
}

interface RootCause {
  status: RootCauseStatus;
  statement: string;
  hypothesis_id: string | null;     // null when status = "insufficient_evidence"
  signature: string | null;         // deterministic signature id when status = "confirmed", e.g. "missing_key_in_upstream_output"
}

interface InvestigationReport {
  summary: string;
  failing_step_id: ID | null;
  root_cause: RootCause;
  facts: Fact[];
  hypotheses: Hypothesis[];
  recommendations: Recommendation[];
  evidence_gaps: string[];          // what data would be needed to be more certain
  relevant_step_ids: ID[];
}

interface Investigation {
  id: ID;
  execution_id: ID;
  status: InvestigationStatus;
  trigger: InvestigationTrigger;
  provider: InvestigationProvider;
  model: string | null;             // "claude-fable-5-2" when provider = fable
  created_at: Timestamp;
  completed_at: Timestamp | null;
  error: ErrorInfo | null;
  report: InvestigationReport | null;   // non-null only when status = completed
}
```

**Honesty rules (enforced in backend code after the model responds):**
1. `root_cause.status = "confirmed"` may only be set by the deterministic signature matcher. If the model returns `confirmed`, the backend downgrades it to `probable`.
2. Any hypothesis citing a fact id that doesn't exist, or a step id that isn't in the trace, is dropped, and a note is appended to `evidence_gaps`.
3. If no hypothesis survives, `root_cause.status = "insufficient_evidence"`.
4. If the LLM call fails or no API key is configured, the `rule_based` provider produces the report (facts + signature-based hypotheses only). The report's `provider` field says so truthfully.

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/investigations/{execution_id}` | `{force?: boolean}` | `202 Investigation` (status `queued`). If a completed one exists and `force` is not true, returns `200` with the existing one. |
| GET | `/investigations/{execution_id}` | — | latest `Investigation` for that execution, or `404` |
| GET | `/investigations` | — | `Page<Investigation>` (with `report`), default sort `-created_at`. Query: `status`, `agent_id` |

The frontend polls `GET /investigations/{execution_id}` every 2 s while the status is `queued` or `running`.

---

## 10. Replays

Replays re-run an execution with its recorded inputs. **Sandbox is the default. In sandbox mode no tool executes for real. Every tool call and LLM call returns the recorded output from the original execution.** Replays are executed by the SDK worker process (the agent's code lives in the developer's process, not in the backend). The backend only coordinates.

```ts
interface RecordedCall {
  step_name: string;
  step_type: StepType;
  tool_name: string | null;
  occurrence: number;       // 1-based index among calls with the same (step_type, tool_name or step_name)
  input: Json;
  output: Json;
  error: ErrorInfo | null;
}

interface ReplayBundle {
  original_execution: ExecutionDetail;
  recorded_calls: RecordedCall[];
}

interface StepDiff {
  ordinal: number;
  name: string;
  original_step_id: ID | null;
  replay_step_id: ID | null;
  change: StepChange;
  original_status: StepStatus | null;
  replay_status: StepStatus | null;
}

interface ReplayComparison {
  original: ExecutionSummary;
  replay: ExecutionSummary;
  outcome: ReplayOutcome;
  duration_delta_ms: number | null;
  tokens_delta: number | null;
  step_count_delta: number;
  step_diffs: StepDiff[];   // aligned by (ordinal, name)
}

interface Replay {
  id: ID;
  original_execution_id: ID;
  replay_execution_id: ID | null;
  mode: ReplayMode;
  status: ReplayStatus;
  side_effects_authorized: boolean;
  note: string | null;
  requested_at: Timestamp;
  claimed_at: Timestamp | null;
  completed_at: Timestamp | null;
  error: ErrorInfo | null;
  comparison: ReplayComparison | null;  // non-null once the replay execution is terminal
}
```

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/executions/{execution_id}/replay` | `{mode: ReplayMode, authorize_side_effects?: boolean, note?: string}` | `201 Replay` (status `pending`). `mode = "live"` without `authorize_side_effects: true` → `422 side_effect_authorization_required` |
| GET | `/replays` | — | `Page<Replay>`, default sort `-requested_at`. Query: `original_execution_id`, `status` |
| GET | `/replays/{replay_id}` | — | `Replay` |
| POST 🔑 | `/replays/{replay_id}/claim` | — | `200 {replay: Replay, bundle: ReplayBundle}`; `409 conflict` if already claimed |
| GET 🔑 | `/replays?status=pending` | — | used by the SDK worker to find work (same endpoint as above, works with or without the key) |

Lifecycle: `pending` → (worker claims) `claimed` → worker creates an execution with `replay_of` and `replay_id` and streams events → when that execution goes terminal, the backend sets the replay to `completed` and computes `comparison`. If the worker reports failure to start, the status is `failed` with `error`.

**Outcome rule:** original failed + replay completed = `fixed`; original completed + replay failed = `regressed`; both failed with the same failing step name and error type = `same_failure`; both failed otherwise = `different_failure`; both completed = `both_succeeded`; anything with `timed_out` or missing data = `inconclusive`.

---

## 11. Health

| Method | Path | Response |
|---|---|---|
| GET | `/health` | `{status: "ok", version: string, database: "ok" \| "error", llm_provider: InvestigationProvider, llm_configured: boolean, llm_model: string \| null}` |

---

## 12. Changelog

| Version | Date | Change | Approved by |
|---|---|---|---|
| 1.0 | 2026-11-14 | Initial contract. Additions over the product spec's suggested endpoints: `/stats/*`, `/executions/{id}/events` (GET), `/investigations` (list), `/replays*`, `/anomalies/{id}`, `/health`. Reason: the dashboard needs aggregates and lists that the suggested endpoints didn't cover, and replay needs a worker handshake. | Jayden, Adit |
| 1.1 | 2026-11-14 | §8: corrected the comment on `Anomaly.execution_id`. It said the field is null for agent-level anomalies, which contradicted the rule table in the same section (`repeated_timeouts`: `execution_id` = most recent one). It now says the field holds the most recent related execution for agent-level anomalies and is null only if none exists. Clarification only: the type is still `ID \| null`, and no field, endpoint or enum changed. | Jayden (made before Adit's kickoff; Adit to confirm) |
