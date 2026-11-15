/**
 * How every enum value of the contract (§1) is presented: a label, an icon and a tone.
 *
 * This is the single place a value's presentation is decided. Each table is a `Record` over the
 * enum, so adding a value to types.ts without presenting it here is a compile error. A value the
 * contract does not know (a newer backend) is shown verbatim and logged; it is never folded into
 * a generic "other".
 */
import {
  ArrowDownToLine,
  ArrowLeftRight,
  ArrowUpFromLine,
  Box,
  Braces,
  CheckCheck,
  Circle,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleDot,
  CircleHelp,
  CircleMinus,
  CircleX,
  Clock,
  ClockAlert,
  DatabaseZap,
  Equal,
  FileDiff,
  Gauge,
  Ghost,
  Hash,
  Hourglass,
  Layers,
  LoaderCircle,
  MessageSquareText,
  Minus,
  OctagonAlert,
  Plus,
  Radio,
  RotateCw,
  Route,
  ShieldCheck,
  Shuffle,
  Timer,
  TrendingDown,
  TriangleAlert,
  Unplug,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";

import type {
  AgentHealth,
  AnomalyStatus,
  AnomalyType,
  Confidence,
  EventType,
  EvidenceKind,
  ExecutionStatus,
  InvestigationProvider,
  InvestigationStatus,
  InvestigationTrigger,
  ReplayMode,
  ReplayOutcome,
  ReplayStatus,
  RootCauseStatus,
  Severity,
  StepChange,
  StepStatus,
  StepType,
} from "@/lib/api/types";

/** Colour carries meaning only. Chrome tones (fg, muted, subtle) are for values with no good/bad reading. */
export type Tone =
  | "completed"
  | "failed"
  | "timed-out"
  | "running"
  | "sev-low"
  | "sev-medium"
  | "sev-high"
  | "sev-critical"
  | "fg"
  | "muted"
  | "subtle";

export const TONE_TEXT: Record<Tone, string> = {
  completed: "text-completed",
  failed: "text-failed",
  "timed-out": "text-timed-out",
  running: "text-running",
  "sev-low": "text-sev-low",
  "sev-medium": "text-sev-medium",
  "sev-high": "text-sev-high",
  "sev-critical": "text-sev-critical",
  fg: "text-fg",
  muted: "text-fg-muted",
  subtle: "text-fg-subtle",
};

export const TONE_BG: Record<Tone, string> = {
  completed: "bg-completed",
  failed: "bg-failed",
  "timed-out": "bg-timed-out",
  running: "bg-running",
  "sev-low": "bg-sev-low",
  "sev-medium": "bg-sev-medium",
  "sev-high": "bg-sev-high",
  "sev-critical": "bg-sev-critical",
  fg: "bg-fg",
  muted: "bg-fg-muted",
  subtle: "bg-fg-subtle",
};

export const TONE_BORDER: Record<Tone, string> = {
  completed: "border-completed",
  failed: "border-failed",
  "timed-out": "border-timed-out",
  running: "border-running",
  "sev-low": "border-sev-low",
  "sev-medium": "border-sev-medium",
  "sev-high": "border-sev-high",
  "sev-critical": "border-sev-critical",
  fg: "border-fg",
  muted: "border-fg-muted",
  subtle: "border-fg-subtle",
};

/** Left-edge accents (anomaly rows, banners). Written out so Tailwind sees each class. */
export const TONE_BORDER_LEFT: Record<Tone, string> = {
  completed: "border-l-completed",
  failed: "border-l-failed",
  "timed-out": "border-l-timed-out",
  running: "border-l-running",
  "sev-low": "border-l-sev-low",
  "sev-medium": "border-l-sev-medium",
  "sev-high": "border-l-sev-high",
  "sev-critical": "border-l-sev-critical",
  fg: "border-l-fg",
  muted: "border-l-fg-muted",
  subtle: "border-l-fg-subtle",
};

export interface EnumMeta {
  label: string;
  icon: LucideIcon;
  tone: Tone;
  /** The icon turns (a spinner). Stilled by prefers-reduced-motion. */
  spin?: boolean;
  /** One sentence for tooltips, where the label alone is not self-explanatory. */
  hint?: string;
}

export const EXECUTION_STATUS: Record<ExecutionStatus, EnumMeta> = {
  running: { label: "Running", icon: LoaderCircle, tone: "running", spin: true },
  completed: { label: "Completed", icon: CircleCheck, tone: "completed" },
  failed: { label: "Failed", icon: CircleX, tone: "failed" },
  timed_out: { label: "Timed out", icon: ClockAlert, tone: "timed-out" },
};

export const STEP_STATUS: Record<StepStatus, EnumMeta> = {
  running: { label: "Running", icon: LoaderCircle, tone: "running", spin: true },
  completed: { label: "Completed", icon: CircleCheck, tone: "completed" },
  failed: { label: "Failed", icon: CircleX, tone: "failed" },
};

export const STEP_TYPE: Record<StepType, EnumMeta> = {
  input: { label: "Input", icon: ArrowDownToLine, tone: "muted" },
  llm_call: { label: "LLM call", icon: MessageSquareText, tone: "muted" },
  tool_call: { label: "Tool call", icon: Wrench, tone: "muted" },
  retrieval: { label: "Retrieval", icon: DatabaseZap, tone: "muted" },
  reasoning: { label: "Reasoning", icon: Route, tone: "muted" },
  output: { label: "Output", icon: ArrowUpFromLine, tone: "muted" },
  custom: { label: "Custom", icon: Box, tone: "muted" },
};

export const SEVERITY: Record<Severity, EnumMeta & { rank: 1 | 2 | 3 | 4 }> = {
  low: { label: "Low", icon: Circle, tone: "sev-low", rank: 1 },
  medium: { label: "Medium", icon: Circle, tone: "sev-medium", rank: 2 },
  high: { label: "High", icon: Circle, tone: "sev-high", rank: 3 },
  critical: { label: "Critical", icon: Circle, tone: "sev-critical", rank: 4 },
};

export const ANOMALY_TYPE: Record<AnomalyType, EnumMeta> = {
  duration_spike: { label: "Duration spike", icon: Timer, tone: "muted", hint: "The run took far longer than the agent's baseline." },
  token_spike: { label: "Token spike", icon: Hash, tone: "muted", hint: "The run used far more tokens than the agent's baseline." },
  repeated_tool_failure: { label: "Repeated tool failure", icon: Unplug, tone: "muted", hint: "The same tool failed repeatedly." },
  excessive_retries: { label: "Excessive retries", icon: RotateCw, tone: "muted", hint: "A step was retried three or more times." },
  repeated_timeouts: { label: "Repeated timeouts", icon: ClockAlert, tone: "muted", hint: "Several of the agent's recent runs timed out." },
  ghost_completion: {
    label: "Ghost completion",
    icon: Ghost,
    tone: "muted",
    hint: "The agent reported success, but the recorded steps say it did not finish.",
  },
  stale_execution: { label: "Stale execution", icon: Hourglass, tone: "muted", hint: "The run went silent and was marked timed out." },
  unexpected_pattern: { label: "Unexpected pattern", icon: Shuffle, tone: "muted", hint: "The run's steps differ from the agent's baseline." },
};

export const ANOMALY_STATUS: Record<AnomalyStatus, EnumMeta> = {
  open: { label: "Open", icon: CircleDot, tone: "fg" },
  acknowledged: { label: "Acknowledged", icon: CircleMinus, tone: "muted" },
  resolved: { label: "Resolved", icon: CircleCheck, tone: "subtle" },
};

export const AGENT_HEALTH: Record<AgentHealth, EnumMeta> = {
  healthy: { label: "Healthy", icon: CircleCheck, tone: "completed", hint: "Success rate of 90% or more and no open high or critical anomaly." },
  degraded: { label: "Degraded", icon: TriangleAlert, tone: "timed-out", hint: "Success rate below 90%, or an open high anomaly." },
  failing: { label: "Failing", icon: OctagonAlert, tone: "failed", hint: "Success rate below 50%, or an open critical anomaly." },
  idle: { label: "Idle", icon: CircleDashed, tone: "subtle", hint: "This agent has never run." },
};

export const INVESTIGATION_STATUS: Record<InvestigationStatus, EnumMeta> = {
  queued: { label: "Queued", icon: Clock, tone: "muted" },
  running: { label: "Investigating", icon: LoaderCircle, tone: "running", spin: true },
  // An investigation that completed is not a success or a failure of the run, so it stays neutral.
  completed: { label: "Completed", icon: CircleCheck, tone: "muted" },
  failed: { label: "Failed", icon: CircleX, tone: "failed" },
};

export const INVESTIGATION_TRIGGER: Record<InvestigationTrigger, EnumMeta> = {
  manual: { label: "Manual", icon: CircleDot, tone: "muted", hint: "Started by a person." },
  auto_failure: { label: "Auto · failure", icon: Zap, tone: "muted", hint: "Started automatically because the run failed or timed out." },
  auto_anomaly: { label: "Auto · anomaly", icon: Zap, tone: "muted", hint: "Started automatically because a high or critical anomaly was raised." },
};

export const INVESTIGATION_PROVIDER: Record<InvestigationProvider, EnumMeta> = {
  fable: { label: "Fable", icon: MessageSquareText, tone: "muted", hint: "Hypotheses were proposed by the language model." },
  rule_based: { label: "Rule-based", icon: Braces, tone: "muted", hint: "Hypotheses come from deterministic signatures only; no model was used." },
};

export const CONFIDENCE: Record<Confidence, EnumMeta & { level: 1 | 2 | 3 }> = {
  low: { label: "Low confidence", icon: Gauge, tone: "muted", level: 1 },
  medium: { label: "Medium confidence", icon: Gauge, tone: "muted", level: 2 },
  high: { label: "High confidence", icon: Gauge, tone: "muted", level: 3 },
};

export const ROOT_CAUSE_STATUS: Record<RootCauseStatus, EnumMeta> = {
  confirmed: { label: "Confirmed", icon: ShieldCheck, tone: "completed", hint: "Matched by a deterministic signature." },
  probable: { label: "Hypothesis", icon: CircleHelp, tone: "timed-out", hint: "A hypothesis; not confirmed." },
  insufficient_evidence: { label: "Insufficient evidence", icon: CircleDashed, tone: "muted", hint: "The recorded evidence does not determine a root cause." },
};

export const EVIDENCE_KIND: Record<EvidenceKind, EnumMeta> = {
  step: { label: "Step", icon: Layers, tone: "muted" },
  event: { label: "Event", icon: Radio, tone: "muted" },
  metric: { label: "Metric", icon: Gauge, tone: "muted" },
  baseline: { label: "Baseline", icon: Equal, tone: "muted" },
  execution: { label: "Execution", icon: Route, tone: "muted" },
  anomaly: { label: "Anomaly", icon: TriangleAlert, tone: "muted" },
};

export const REPLAY_MODE: Record<ReplayMode, EnumMeta> = {
  sandbox: { label: "Sandbox", icon: ShieldCheck, tone: "muted", hint: "Tool calls returned recorded outputs. Nothing external ran." },
  live: { label: "Live", icon: CircleAlert, tone: "timed-out", hint: "Tools ran for real, with side effects authorized." },
};

export const REPLAY_STATUS: Record<ReplayStatus, EnumMeta> = {
  pending: { label: "Pending", icon: Clock, tone: "muted", hint: "Waiting for a replay worker to claim it." },
  claimed: { label: "Replaying", icon: LoaderCircle, tone: "running", spin: true, hint: "A replay worker is running it." },
  completed: { label: "Completed", icon: CircleCheck, tone: "muted" },
  failed: { label: "Failed", icon: CircleX, tone: "failed", hint: "The replay could not be run." },
};

export const REPLAY_OUTCOME: Record<ReplayOutcome, EnumMeta> = {
  fixed: { label: "Fixed", icon: CircleCheck, tone: "completed", hint: "The original failed; the replay completed." },
  regressed: { label: "Regressed", icon: TrendingDown, tone: "failed", hint: "The original completed; the replay failed." },
  same_failure: { label: "Same failure", icon: Equal, tone: "failed", hint: "Both failed at the same step with the same error type." },
  different_failure: { label: "Different failure", icon: Shuffle, tone: "timed-out", hint: "Both failed, but not in the same way." },
  both_succeeded: { label: "Both succeeded", icon: CheckCheck, tone: "muted", hint: "The original and the replay both completed." },
  inconclusive: { label: "Inconclusive", icon: CircleHelp, tone: "subtle", hint: "A timeout or missing data prevents a comparison." },
};

export const STEP_CHANGE: Record<StepChange, EnumMeta> = {
  unchanged: { label: "Unchanged", icon: Equal, tone: "subtle" },
  status_changed: { label: "Status changed", icon: ArrowLeftRight, tone: "fg" },
  output_changed: { label: "Output changed", icon: FileDiff, tone: "fg" },
  added: { label: "Added", icon: Plus, tone: "fg" },
  removed: { label: "Removed", icon: Minus, tone: "fg" },
};

export const EVENT_TYPE: Record<EventType, EnumMeta> = {
  "step.started": { label: "step.started", icon: Circle, tone: "muted" },
  "step.completed": { label: "step.completed", icon: Circle, tone: "muted" },
  "step.failed": { label: "step.failed", icon: Circle, tone: "failed" },
  "execution.completed": { label: "execution.completed", icon: Circle, tone: "fg" },
  "execution.failed": { label: "execution.failed", icon: Circle, tone: "failed" },
  "execution.timed_out": { label: "execution.timed_out", icon: Circle, tone: "timed-out" },
  log: { label: "log", icon: Circle, tone: "subtle" },
};

const reported = new Set<string>();

/**
 * The presentation of `value`, or — for a value the contract does not define — the raw value with
 * a neutral look, reported once in the console.
 */
export function metaOf<K extends string, M extends EnumMeta>(table: Record<K, M>, value: string, enumName: string): M | EnumMeta {
  const known = (table as Record<string, M>)[value];
  if (known) return known;
  const key = `${enumName}:${value}`;
  if (!reported.has(key)) {
    reported.add(key);
    console.error(`[ghostwatch] ${enumName} has a value the contract does not define: "${value}".`);
  }
  return { label: value, icon: CircleHelp, tone: "subtle" };
}
