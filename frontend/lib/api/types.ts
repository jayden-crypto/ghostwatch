/**
 * Mirror of contract/API_CONTRACT.md v1.1. Section numbers refer to that file.
 *
 * Keys are snake_case exactly as they cross the wire: nothing here is renamed or converted.
 * Every listed key is always present; "absent" is `null`, never a missing key.
 * If this file and the contract disagree, this file is wrong.
 */

// ── §1 Enums ────────────────────────────────────────────────────────────────

export const EXECUTION_STATUSES = ["running", "completed", "failed", "timed_out"] as const;
export type ExecutionStatus = (typeof EXECUTION_STATUSES)[number];

export const STEP_STATUSES = ["running", "completed", "failed"] as const;
export type StepStatus = (typeof STEP_STATUSES)[number];

export const STEP_TYPES = [
  "input",
  "llm_call",
  "tool_call",
  "retrieval",
  "reasoning",
  "output",
  "custom",
] as const;
export type StepType = (typeof STEP_TYPES)[number];

export const SEVERITIES = ["low", "medium", "high", "critical"] as const;
export type Severity = (typeof SEVERITIES)[number];

export const ANOMALY_TYPES = [
  "duration_spike",
  "token_spike",
  "repeated_tool_failure",
  "excessive_retries",
  "repeated_timeouts",
  "ghost_completion",
  "stale_execution",
  "unexpected_pattern",
] as const;
export type AnomalyType = (typeof ANOMALY_TYPES)[number];

export const ANOMALY_STATUSES = ["open", "acknowledged", "resolved"] as const;
export type AnomalyStatus = (typeof ANOMALY_STATUSES)[number];

export const AGENT_HEALTHS = ["healthy", "degraded", "failing", "idle"] as const;
export type AgentHealth = (typeof AGENT_HEALTHS)[number];

export const INVESTIGATION_STATUSES = ["queued", "running", "completed", "failed"] as const;
export type InvestigationStatus = (typeof INVESTIGATION_STATUSES)[number];

export const INVESTIGATION_TRIGGERS = ["manual", "auto_failure", "auto_anomaly"] as const;
export type InvestigationTrigger = (typeof INVESTIGATION_TRIGGERS)[number];

export const INVESTIGATION_PROVIDERS = ["fable", "rule_based"] as const;
export type InvestigationProvider = (typeof INVESTIGATION_PROVIDERS)[number];

export const CONFIDENCES = ["low", "medium", "high"] as const;
export type Confidence = (typeof CONFIDENCES)[number];

export const ROOT_CAUSE_STATUSES = ["confirmed", "probable", "insufficient_evidence"] as const;
export type RootCauseStatus = (typeof ROOT_CAUSE_STATUSES)[number];

export const EVIDENCE_KINDS = ["step", "event", "metric", "baseline", "execution", "anomaly"] as const;
export type EvidenceKind = (typeof EVIDENCE_KINDS)[number];

export const REPLAY_MODES = ["sandbox", "live"] as const;
export type ReplayMode = (typeof REPLAY_MODES)[number];

export const REPLAY_STATUSES = ["pending", "claimed", "completed", "failed"] as const;
export type ReplayStatus = (typeof REPLAY_STATUSES)[number];

export const REPLAY_OUTCOMES = [
  "same_failure",
  "different_failure",
  "fixed",
  "regressed",
  "both_succeeded",
  "inconclusive",
] as const;
export type ReplayOutcome = (typeof REPLAY_OUTCOMES)[number];

export const STEP_CHANGES = ["unchanged", "status_changed", "output_changed", "added", "removed"] as const;
export type StepChange = (typeof STEP_CHANGES)[number];

export const EVENT_TYPES = [
  "step.started",
  "step.completed",
  "step.failed",
  "execution.completed",
  "execution.failed",
  "execution.timed_out",
  "log",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

export const LOG_LEVELS = ["debug", "info", "warning", "error"] as const;
export type LogLevel = (typeof LOG_LEVELS)[number];

/** §0 error table. */
export const ERROR_CODES = [
  "bad_request",
  "unauthorized",
  "not_found",
  "conflict",
  "execution_already_terminal",
  "validation_error",
  "side_effect_authorization_required",
  "internal_error",
  "llm_unavailable",
] as const;
export type ErrorCode = (typeof ERROR_CODES)[number];

export const STATS_WINDOWS = ["24h", "7d", "30d"] as const;
export type StatsWindow = (typeof STATS_WINDOWS)[number];

export const STATS_BUCKETS = ["hour", "day"] as const;
export type StatsBucket = (typeof STATS_BUCKETS)[number];

// ── §2 Shared types ─────────────────────────────────────────────────────────

/** Prefixed opaque id (`exe_` + 32 lowercase hex). Never parsed. */
export type ID = string;
/** ISO 8601, UTC, millisecond precision, `Z` suffix. */
export type Timestamp = string;
export type Json = null | boolean | number | string | Json[] | { [k: string]: Json };

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ErrorInfo {
  type: string;
  message: string;
  stacktrace: string | null;
}

export interface Evidence {
  kind: EvidenceKind;
  label: string;
  ref_id: ID | null;
  field: string | null;
  observed: Json;
  expected: Json;
  excerpt: string | null;
}

/** §0: what a payload field larger than 64 KB is stored as. */
export interface TruncatedPayload {
  _truncated: true;
  original_bytes: number;
  preview: string;
}

/** §0: body of every non-2xx response. */
export interface ErrorEnvelope {
  error: {
    code: ErrorCode;
    message: string;
    details: Json;
  };
}

// ── §3 Agents ───────────────────────────────────────────────────────────────

export interface AgentStats {
  total_executions: number;
  completed: number;
  failed: number;
  timed_out: number;
  running: number;
  success_rate: number | null;
  avg_duration_ms: number | null;
  open_anomalies: number;
  last_execution: ExecutionSummary | null;
  health: AgentHealth;
}

export interface Agent {
  id: ID;
  name: string;
  slug: string;
  description: string | null;
  framework: string | null;
  metadata: { [k: string]: Json };
  created_at: Timestamp;
  stats: AgentStats;
}

// ── §4 Executions ───────────────────────────────────────────────────────────

export interface ExecutionSummary {
  id: ID;
  agent_id: ID;
  agent_name: string;
  status: ExecutionStatus;
  started_at: Timestamp;
  ended_at: Timestamp | null;
  duration_ms: number | null;
  step_count: number;
  tokens_total: number | null;
  cost_usd: number | null;
  anomaly_count: number;
  has_investigation: boolean;
  replay_of: ID | null;
  error: ErrorInfo | null;
}

export interface ExecutionConfig {
  model: string | null;
  params: { [k: string]: Json };
  expected_steps: string[] | null;
  timeout_ms: number | null;
  /** Free-form extras are allowed. */
  [k: string]: Json;
}

export interface ExecutionDetail extends ExecutionSummary {
  input: Json;
  output: Json;
  config: ExecutionConfig;
  tokens_input: number | null;
  tokens_output: number | null;
  tags: string[];
  replay_ids: ID[];
}

// ── §5 Events ───────────────────────────────────────────────────────────────

/** Response of POST /executions/{id}/events. The dashboard never calls it; typed for the fixtures. */
export interface IngestResponse {
  accepted: number;
  duplicates: number;
  execution_status: ExecutionStatus;
}

/**
 * One row of GET /executions/{id}/events (§6). The contract leaves this type unnamed; the name
 * matches the backend's schema. `payload` depends on `type` (§5) and is shown as recorded.
 */
export interface StoredEvent {
  id: ID;
  seq: number;
  type: EventType;
  timestamp: Timestamp;
  received_at: Timestamp;
  payload: { [k: string]: Json };
}

// ── §6 Traces ───────────────────────────────────────────────────────────────

export interface Step {
  id: ID;
  execution_id: ID;
  parent_step_id: ID | null;
  ordinal: number;
  depth: number;
  name: string;
  type: StepType;
  status: StepStatus;
  started_at: Timestamp;
  ended_at: Timestamp | null;
  duration_ms: number | null;
  offset_ms: number;
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

export interface Trace {
  execution: ExecutionDetail;
  steps: Step[];
  anomalies: Anomaly[];
  event_count: number;
}

// ── §7 Stats ────────────────────────────────────────────────────────────────

export interface StatsOverview {
  window: StatsWindow;
  total_agents: number;
  total_executions: number;
  completed: number;
  failed: number;
  timed_out: number;
  running: number;
  success_rate: number | null;
  avg_duration_ms: number | null;
  open_anomalies: number;
}

export interface TimeseriesPoint {
  bucket_start: Timestamp;
  completed: number;
  failed: number;
  timed_out: number;
  avg_duration_ms: number | null;
}

export interface StatsTimeseries {
  window: StatsWindow;
  bucket: StatsBucket;
  points: TimeseriesPoint[];
}

// ── §8 Anomalies ────────────────────────────────────────────────────────────

export interface Anomaly {
  id: ID;
  type: AnomalyType;
  severity: Severity;
  status: AnomalyStatus;
  agent_id: ID;
  agent_name: string;
  /** For agent-level anomalies: the most recent related execution. Null only if none exists. */
  execution_id: ID | null;
  detected_at: Timestamp;
  rule_id: string;
  title: string;
  explanation: string;
  evidence: Evidence[];
}

// ── §9 Investigations ───────────────────────────────────────────────────────

export interface Fact {
  id: string;
  statement: string;
  evidence: Evidence[];
}

export interface Hypothesis {
  id: string;
  statement: string;
  confidence: Confidence;
  reasoning: string;
  supporting_fact_ids: string[];
  contradicting_fact_ids: string[];
}

export interface Recommendation {
  id: string;
  action: string;
  rationale: string;
  hypothesis_id: string | null;
}

export interface RootCause {
  status: RootCauseStatus;
  statement: string;
  hypothesis_id: string | null;
  signature: string | null;
}

export interface InvestigationReport {
  summary: string;
  failing_step_id: ID | null;
  root_cause: RootCause;
  facts: Fact[];
  hypotheses: Hypothesis[];
  recommendations: Recommendation[];
  evidence_gaps: string[];
  relevant_step_ids: ID[];
}

export interface Investigation {
  id: ID;
  execution_id: ID;
  status: InvestigationStatus;
  trigger: InvestigationTrigger;
  provider: InvestigationProvider;
  model: string | null;
  created_at: Timestamp;
  completed_at: Timestamp | null;
  error: ErrorInfo | null;
  report: InvestigationReport | null;
}

// ── §10 Replays ─────────────────────────────────────────────────────────────

export interface RecordedCall {
  step_name: string;
  step_type: StepType;
  tool_name: string | null;
  occurrence: number;
  input: Json;
  output: Json;
  error: ErrorInfo | null;
}

export interface ReplayBundle {
  original_execution: ExecutionDetail;
  recorded_calls: RecordedCall[];
}

export interface StepDiff {
  ordinal: number;
  name: string;
  original_step_id: ID | null;
  replay_step_id: ID | null;
  change: StepChange;
  original_status: StepStatus | null;
  replay_status: StepStatus | null;
}

export interface ReplayComparison {
  original: ExecutionSummary;
  replay: ExecutionSummary;
  outcome: ReplayOutcome;
  duration_delta_ms: number | null;
  tokens_delta: number | null;
  step_count_delta: number;
  step_diffs: StepDiff[];
}

export interface Replay {
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
  comparison: ReplayComparison | null;
}

/** Response of POST /replays/{id}/claim. Used by the SDK worker only; typed for the fixtures. */
export interface ReplayClaim {
  replay: Replay;
  bundle: ReplayBundle;
}

// ── §11 Health ──────────────────────────────────────────────────────────────

export interface Health {
  status: "ok";
  version: string;
  database: "ok" | "error";
  llm_provider: InvestigationProvider;
  llm_configured: boolean;
  llm_model: string | null;
}

// ── Request bodies and query params the dashboard sends ─────────────────────

/** GET /agents (§3). */
export interface AgentListParams {
  q?: string;
  health?: AgentHealth[];
  sort?: string;
  limit?: number;
  offset?: number;
}

export const EXECUTION_SORT_FIELDS = ["started_at", "duration_ms", "tokens_total", "cost_usd"] as const;
export type ExecutionSortField = (typeof EXECUTION_SORT_FIELDS)[number];
export type ExecutionSort = ExecutionSortField | `-${ExecutionSortField}`;

/** GET /executions (§4). */
export interface ExecutionListParams {
  agent_id?: ID;
  status?: ExecutionStatus[];
  started_after?: Timestamp;
  started_before?: Timestamp;
  min_duration_ms?: number;
  max_duration_ms?: number;
  has_anomaly?: boolean;
  is_replay?: boolean;
  replay_of?: ID;
  q?: string;
  sort?: ExecutionSort;
  limit?: number;
  offset?: number;
}

/** GET /executions/{id}/events (§6). */
export interface EventListParams {
  limit?: number;
  offset?: number;
}

/** GET /stats/timeseries (§7). */
export interface TimeseriesParams {
  window?: StatsWindow;
  bucket?: StatsBucket;
  agent_id?: ID;
}

/** GET /anomalies (§8). */
export interface AnomalyListParams {
  agent_id?: ID;
  execution_id?: ID;
  type?: AnomalyType;
  severity?: Severity[];
  status?: AnomalyStatus[];
  limit?: number;
  offset?: number;
}

/** GET /investigations (§9). */
export interface InvestigationListParams {
  status?: InvestigationStatus;
  agent_id?: ID;
  limit?: number;
  offset?: number;
}

/** POST /investigations/{execution_id} (§9). */
export interface InvestigationCreateBody {
  force?: boolean;
}

/** GET /replays (§10). */
export interface ReplayListParams {
  original_execution_id?: ID;
  status?: ReplayStatus;
  limit?: number;
  offset?: number;
}

/** POST /executions/{execution_id}/replay (§10). */
export interface ReplayCreateBody {
  mode: ReplayMode;
  authorize_side_effects?: boolean;
  note?: string;
}

/** PATCH /anomalies/{anomaly_id} (§8, P1). */
export interface AnomalyUpdateBody {
  status: AnomalyStatus;
}
