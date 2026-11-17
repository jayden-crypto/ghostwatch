/**
 * The eight anomaly rules of contract §8, written to produce the same titles, explanations and
 * evidence as the backend's `app/services/anomaly/rules.py` (jayden/backend at e9f4c53), so mock
 * mode reads exactly like live mode. Thresholds are the contract's.
 */
import type { Anomaly, AnomalyType, Evidence, ExecutionDetail, Json, Severity, Step } from "../../lib/api/types";
import { iso, type Run } from "./world";

export interface RunView {
  run: Run;
  detail: ExecutionDetail;
  steps: Step[];
}

export interface AnomalyDraft {
  type: AnomalyType;
  severity: Severity;
  title: string;
  explanation: string;
  evidence: Evidence[];
}

const MIN_BASELINE_RUNS = 5;
const BASELINE_SIZE = 20;
const MAX_EVIDENCE_ITEMS = 10;
const DEFAULT_TIMEOUT_MS = 300_000;

export const evidence = (
  kind: Evidence["kind"],
  label: string,
  rest: Partial<Omit<Evidence, "kind" | "label">> = {},
): Evidence => ({
  kind,
  label,
  ref_id: rest.ref_id ?? null,
  field: rest.field ?? null,
  observed: rest.observed ?? null,
  expected: rest.expected ?? null,
  excerpt: rest.excerpt == null ? null : rest.excerpt.slice(0, 500),
});

/** 12,400 for whole numbers, 12,400.5 otherwise. */
export const num = (value: number): string =>
  Number.isInteger(value)
    ? value.toLocaleString("en-US")
    : value.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export const plural = (count: number, noun: string): string => `${count} ${noun}${count === 1 ? "" : "s"}`;

export const stepLabel = (step: Step): string =>
  `Step ${step.ordinal} ${step.name}${step.attempt > 1 ? ` (attempt ${step.attempt})` : ""}`;

export const median = (values: number[]): number => {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};

/** Nearest-rank 95th percentile. */
export const p95 = (values: number[]): number => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.ceil(0.95 * sorted.length) - 1];
};

export interface Baseline {
  runs: number;
  durations: number[];
  tokens: number[];
  maxStepCount: number;
  tools: string[];
}

/** The agent's last 20 completed, non-replay executions that started before this one. */
export function baselineFor(view: RunView, all: RunView[]): Baseline {
  const runs = all
    .filter(
      (other) =>
        other.run.agent === view.run.agent &&
        other.run !== view.run &&
        other.run.replayOf === null &&
        other.detail.status === "completed" &&
        other.run.startedAt <= view.run.startedAt,
    )
    .sort((a, b) => b.run.startedAt - a.run.startedAt)
    .slice(0, BASELINE_SIZE);
  return {
    runs: runs.length,
    durations: runs.map((r) => r.detail.duration_ms!),
    tokens: runs.flatMap((r) => (r.detail.tokens_total === null ? [] : [r.detail.tokens_total])),
    maxStepCount: Math.max(0, ...runs.map((r) => r.detail.step_count)),
    tools: [...new Set(runs.flatMap((r) => r.steps.flatMap((s) => (s.tool_name ? [s.tool_name] : []))))].sort(),
  };
}

/** The agent's last terminal, non-replay executions up to this one, newest first; this one leads. */
function recentRuns(view: RunView, all: RunView[]): RunView[] {
  const others = all
    .filter(
      (other) =>
        other.run.agent === view.run.agent &&
        other.run !== view.run &&
        other.run.replayOf === null &&
        other.detail.status !== "running" &&
        other.run.startedAt <= view.run.startedAt,
    )
    .sort((a, b) => b.run.startedAt - a.run.startedAt)
    .slice(0, 9);
  return [view, ...others];
}

function spike(
  view: RunView,
  o: {
    type: AnomalyType;
    quantity: string;
    unit: string;
    field: string;
    observed: number;
    values: number[];
    medianFactor: number;
    p95Factor: number;
    highFactor: number;
  },
): AnomalyDraft | null {
  const med = median(o.values);
  const high = p95(o.values);
  const threshold = Math.max(o.medianFactor * med, o.p95Factor * high);
  if (o.observed <= threshold) return null;
  const quantity = o.quantity[0].toUpperCase() + o.quantity.slice(1);
  const p95Term = o.p95Factor === 1 ? "p95" : `${num(o.p95Factor)}× p95`;
  return {
    type: o.type,
    severity: o.observed > o.highFactor * med ? "high" : "medium",
    title: `${quantity} ${(o.observed / med).toFixed(1)}× above baseline`,
    explanation:
      `Execution ${o.unit === "ms" ? "took" : "used"} ${num(o.observed)} ${o.unit}. Baseline median for ` +
      `${view.run.agent.slug} is ${num(med)} ${o.unit} over ${plural(o.values.length, "run")} ` +
      `(p95 ${num(high)} ${o.unit}). Rule fires above max(${num(o.medianFactor)}× median, ${p95Term}) = ` +
      `${num(threshold)} ${o.unit}. Severity is high above ${num(o.highFactor)}× median = ` +
      `${num(o.highFactor * med)} ${o.unit}.`,
    evidence: [
      evidence("execution", `${quantity} of this execution`, {
        ref_id: view.detail.id,
        field: o.field,
        observed: o.observed,
        expected: threshold,
      }),
      evidence("baseline", `Baseline ${o.quantity} over ${plural(o.values.length, "completed run")}`, {
        field: o.field,
        observed: { median: med, p95: high, runs: o.values.length },
      }),
    ],
  };
}

const failedStepEvidence = (step: Step): Evidence =>
  evidence("step", `${stepLabel(step)} failed`, {
    ref_id: step.id,
    field: "error.message",
    observed: step.error?.message ?? null,
    excerpt: step.error?.message ?? null,
  });

export function detect(view: RunView, all: RunView[]): AnomalyDraft[] {
  const { detail, steps, run } = view;
  if (detail.status === "running") return [];
  const baseline = baselineFor(view, all);
  const sufficient = baseline.runs >= MIN_BASELINE_RUNS;
  const drafts: (AnomalyDraft | null)[] = [];

  // duration_spike
  if (detail.duration_ms !== null && sufficient) {
    drafts.push(
      spike(view, {
        type: "duration_spike",
        quantity: "duration",
        unit: "ms",
        field: "duration_ms",
        observed: detail.duration_ms,
        values: baseline.durations,
        medianFactor: 3,
        p95Factor: 1.5,
        highFactor: 5,
      }),
    );
  }

  // token_spike
  if (detail.tokens_total !== null && baseline.tokens.length >= MIN_BASELINE_RUNS) {
    drafts.push(
      spike(view, {
        type: "token_spike",
        quantity: "token usage",
        unit: "tokens",
        field: "tokens_total",
        observed: detail.tokens_total,
        values: baseline.tokens,
        medianFactor: 2,
        p95Factor: 1,
        highFactor: 4,
      }),
    );
  }

  // repeated_tool_failure (the within-one-execution form; the fixture world has no 3-run streak)
  const failedTools = steps.filter((s) => s.status === "failed" && s.tool_name);
  const counts = new Map<string, Step[]>();
  for (const step of failedTools) counts.set(step.tool_name!, [...(counts.get(step.tool_name!) ?? []), step]);
  const repeated = [...counts.entries()].filter(([, list]) => list.length >= 3).sort(([a], [b]) => a.localeCompare(b))[0];
  if (repeated) {
    const [tool, list] = repeated;
    drafts.push({
      type: "repeated_tool_failure",
      severity: "high",
      title: `Tool ${tool} failed ${list.length} times in one execution`.slice(0, 80),
      explanation:
        `Tool ${tool} has ${list.length} failed steps in this execution. Rule fires at 3 or more failed ` +
        "steps of the same tool in one execution.",
      evidence: list.slice(0, MAX_EVIDENCE_ITEMS).map(failedStepEvidence),
    });
  }

  // excessive_retries
  const retried = steps.filter((s) => s.attempt > 1);
  const highest = Math.max(1, ...retried.map((s) => s.attempt));
  const totalRetries = steps.reduce((sum, s) => sum + s.attempt - 1, 0);
  if (highest >= 3 || totalRetries >= 5) {
    drafts.push({
      type: "excessive_retries",
      severity: "medium",
      title: `${plural(retried.length, "retried step")}, highest attempt ${highest}`,
      explanation:
        `The highest attempt number in this execution is ${highest} and the sum of (attempt - 1) over all ` +
        `steps is ${totalRetries}. Rule fires when any step has attempt >= 3 or the sum is >= 5.`,
      evidence: [...retried]
        .sort((a, b) => b.attempt - a.attempt || a.ordinal - b.ordinal)
        .slice(0, MAX_EVIDENCE_ITEMS)
        .map((step) =>
          evidence("step", `${stepLabel(step)} is a retry`, {
            ref_id: step.id,
            field: "attempt",
            observed: step.attempt,
            expected: "below 3",
          }),
        ),
    });
  }

  // repeated_timeouts (agent-level; raised on the execution that is itself a timeout)
  const window = recentRuns(view, all);
  const timedOut = window.filter((r) => r.detail.status === "timed_out");
  if (detail.status === "timed_out" && timedOut.length >= 3) {
    drafts.push({
      type: "repeated_timeouts",
      severity: "high",
      title: `${timedOut.length} of the last ${window.length} executions timed out`,
      explanation:
        `${timedOut.length} of the last ${window.length} executions of ${run.agent.slug} timed out, including ` +
        "this one. Rule fires at 3 or more timeouts in the agent's last 10 executions.",
      evidence: timedOut.map((r) =>
        evidence("execution", r === view ? "This execution timed out" : "Earlier timed-out execution", {
          ref_id: r.detail.id,
          field: "status",
          observed: "timed_out",
        }),
      ),
    });
  }

  // ghost_completion
  if (detail.status === "completed") {
    const reasons: string[] = [];
    const items: Evidence[] = [];
    if (steps.length === 0) {
      reasons.push("no steps were recorded");
      items.push(
        evidence("execution", "Execution completed without recording any step", {
          ref_id: detail.id,
          field: "step_count",
          observed: 0,
          expected: "at least 1",
        }),
      );
    }
    const completedNames = steps.filter((s) => s.status === "completed").map((s) => s.name);
    const expectedSteps = detail.config.expected_steps ?? [];
    const missing = [...new Set(expectedSteps)].filter((name) => !completedNames.includes(name));
    for (const name of missing) {
      const last = steps.filter((s) => s.name === name).at(-1);
      items.push(
        last
          ? evidence("step", `Expected step ${name} never completed (last seen as ${last.status})`, {
              ref_id: last.id,
              field: "status",
              observed: last.status,
              expected: "completed",
            })
          : evidence("execution", `Expected step ${name} never started`, {
              ref_id: detail.id,
              field: "config.expected_steps",
              observed: [...new Set(completedNames)],
              expected: expectedSteps,
            }),
      );
    }
    if (missing.length) {
      reasons.push(`expected ${plural(missing.length, "step")} never completed: ${missing.join(", ")}`);
    }
    const running = steps.filter((s) => s.status === "running");
    for (const step of running) {
      items.push(
        evidence("step", `${stepLabel(step)} was still running when the execution completed`, {
          ref_id: step.id,
          field: "status",
          observed: "running",
          expected: "completed",
        }),
      );
    }
    if (running.length) {
      reasons.push(`${plural(running.length, "step")} still running: ${running.map((s) => s.name).join(", ")}`);
    }
    if (reasons.length) {
      drafts.push({
        type: "ghost_completion",
        severity: "critical",
        title: missing.length
          ? `Reported completed, but ${missing[0]} never completed`
          : running.length
            ? `Reported completed while ${running[0].name} was still running`
            : "Reported completed without recording any step",
        explanation:
          `The execution reported status completed, but ${reasons.join("; ")}. Rule fires when a completed ` +
          "execution has a step still running, an expected step (config.expected_steps) with no completed " +
          "step, or no steps at all.",
        evidence: items.slice(0, MAX_EVIDENCE_ITEMS),
      });
    }
  }

  // stale_execution
  if (run.end?.status === "timed_out") {
    const timeoutMs = detail.config.timeout_ms ?? DEFAULT_TIMEOUT_MS;
    const idleMs = run.end.at - run.end.lastEventAt;
    const lastEventAt = iso(run.startedAt + run.end.lastEventAt);
    drafts.push({
      type: "stale_execution",
      severity: "high",
      title: `No event for ${num(idleMs)} ms; marked timed out`,
      explanation:
        `The execution was running and sent no event for ${num(idleMs)} ms (last event received at ` +
        `${lastEventAt}). Rule fires after config.timeout_ms = ${num(timeoutMs)} ms without an event; ` +
        "Ghostwatch then marked the execution timed_out.",
      evidence: [
        evidence("execution", "Time since the last event was received", {
          ref_id: detail.id,
          field: "last_event_at",
          observed: { last_event_at: lastEventAt, idle_ms: idleMs },
          expected: { timeout_ms: timeoutMs },
        }),
      ],
    });
  }

  // unexpected_pattern
  if (sufficient) {
    const reasons: string[] = [];
    const items: Evidence[] = [];
    const newToolSteps = steps.filter((s) => s.tool_name && !baseline.tools.includes(s.tool_name));
    const newTools = [...new Set(newToolSteps.map((s) => s.tool_name!))];
    if (newTools.length) {
      reasons.push(
        `it called ${plural(newTools.length, "tool")} never seen in the baseline: ${newTools.join(", ")} ` +
          `(baseline tools: ${baseline.tools.join(", ") || "none"})`,
      );
      for (const tool of newTools) {
        const step = newToolSteps.find((s) => s.tool_name === tool)!;
        items.push(
          evidence("step", `${stepLabel(step)} calls a tool not seen in the baseline`, {
            ref_id: step.id,
            field: "tool_name",
            observed: tool,
            expected: baseline.tools as Json,
          }),
        );
      }
    }
    const stepLimit = 2 * baseline.maxStepCount;
    if (detail.step_count > stepLimit) {
      reasons.push(
        `it recorded ${plural(detail.step_count, "step")}, above 2× the largest baseline step count ` +
          `(${baseline.maxStepCount}) = ${stepLimit}`,
      );
      items.push(
        evidence("execution", "Number of steps in this execution", {
          ref_id: detail.id,
          field: "step_count",
          observed: detail.step_count,
          expected: stepLimit,
        }),
      );
    }
    if (reasons.length) {
      drafts.push({
        type: "unexpected_pattern",
        severity: "low",
        title: newTools.length
          ? `New tool in this run: ${newTools[0]}`
          : `${detail.step_count} steps, baseline maximum is ${baseline.maxStepCount}`,
        explanation:
          `Compared with the last ${plural(baseline.runs, "completed run")} of ${run.agent.slug}, ` +
          `${reasons.join(" and ")}. Rule fires on a tool never seen in the baseline or on step_count above ` +
          "2× the baseline maximum.",
        evidence: items.slice(0, MAX_EVIDENCE_ITEMS),
      });
    }
  }

  return drafts.filter((draft): draft is AnomalyDraft => draft !== null);
}

export function toAnomaly(view: RunView, draft: AnomalyDraft, id: string, status: Anomaly["status"]): Anomaly {
  return {
    id,
    type: draft.type,
    severity: draft.severity,
    status,
    agent_id: view.detail.agent_id,
    agent_name: view.detail.agent_name,
    execution_id: view.detail.id,
    detected_at: view.detail.ended_at!,
    rule_id: `${draft.type}.v1`,
    title: draft.title,
    explanation: draft.explanation,
    evidence: draft.evidence,
  };
}
