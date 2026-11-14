/**
 * Investigation reports for the fixture world, written to produce the same facts, signatures and
 * wording as the backend's `app/services/investigation/` (jayden/backend at e9f4c53).
 *
 * Facts and signature matches are computed from the recorded steps. Hypotheses attributed to the
 * LLM are written by hand in story.ts and may only cite facts built here, as in the real pipeline.
 */
import type {
  Anomaly,
  Confidence,
  Evidence,
  Fact,
  Hypothesis,
  ID,
  InvestigationReport,
  Json,
  Recommendation,
  RootCause,
  Step,
} from "../../lib/api/types";
import { baselineFor, evidence, median, p95, stepLabel, type RunView } from "./anomalies";

const errorText = (error: Step["error"]): string =>
  error ? `${error.type}: ${error.message}` : "no error recorded";

const excerptOf = (value: Json): string => (typeof value === "string" ? value : JSON.stringify(value)).slice(0, 500);

const isObject = (value: Json): value is { [k: string]: Json } =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isTruncated = (value: Json): boolean => isObject(value) && value._truncated === true;

const HTTP_IN_TEXT = /(?:HTTP\w*|\bstatus(?:[ _]code)?)\D{0,3}([45]\d\d)\b/i;

function httpStatusOf(step: Step): number | null {
  if (!step.tool_name) return null;
  if (isObject(step.output)) {
    for (const key of ["status", "status_code", "http_status"]) {
      const value = step.output[key];
      if (typeof value === "number" && Number.isInteger(value) && value >= 400 && value <= 599) return value;
    }
  }
  const match = step.error && HTTP_IN_TEXT.exec(`${step.error.type} ${step.error.message}`);
  return match ? Number(match[1]) : null;
}

function describeOutput(output: Json): [string, Json] {
  if (output === null) return ["has no output", null];
  if (isObject(output) && output._truncated === true) {
    return [
      `has an output that was truncated at ingestion (${output.original_bytes} bytes; only a preview is stored)`,
      output,
    ];
  }
  if (isObject(output)) {
    const keys = Object.keys(output).sort();
    return [`returned an object with keys: ${keys.length ? keys.join(", ") : "(none)"}`, keys];
  }
  if (Array.isArray(output)) return [`returned a list of ${output.length} items`, { type: "list", length: output.length }];
  const pythonType = typeof output === "string" ? "str" : typeof output === "boolean" ? "bool" : Number.isInteger(output) ? "int" : "float";
  return [`returned a ${pythonType} value`, output];
}

interface FactSet {
  facts: Fact[];
  /** Internal key → fact id. Keys: outcome, execution_error, failing_step, output:<ordinal>, retry:<name>, http:<ordinal>, running_steps, expected_steps, anomaly:<type>, baseline. */
  ids: Map<string, string>;
  gaps: string[];
  failing: Step | null;
  httpStatuses: Map<ID, number>;
}

function buildFacts(view: RunView, anomalies: Anomaly[], all: RunView[]): FactSet {
  const { detail, steps, run } = view;
  const set: FactSet = { facts: [], ids: new Map(), gaps: [], failing: null, httpStatuses: new Map() };
  const add = (key: string, statement: string, items: Evidence[]) => {
    const id = `F${set.facts.length + 1}`;
    set.facts.push({ id, statement, evidence: items.slice(0, 10) });
    set.ids.set(key, id);
  };

  if (detail.status === "failed") {
    const failed = steps.filter((s) => s.status === "failed");
    const same = failed.filter((s) => s.error?.type === detail.error?.type && s.error?.message === detail.error?.message);
    set.failing = (same.length ? same : failed).at(-1) ?? null;
  } else if (detail.status === "timed_out") {
    set.failing = steps.filter((s) => s.status === "running").at(-1) ?? null;
  }
  const failing = set.failing;

  add(
    "outcome",
    `Execution of ${run.agent.slug} ended with status ${detail.status} after ${detail.duration_ms} ms and ` +
      `${detail.step_count} steps.`,
    [evidence("execution", "Final status of the execution", { ref_id: detail.id, field: "status", observed: detail.status })],
  );
  if (detail.error) {
    add("execution_error", `The execution ended with the error ${errorText(detail.error)}.`, [
      evidence("execution", "Terminal error of the execution", {
        ref_id: detail.id,
        field: "error.message",
        observed: detail.error.message,
        excerpt: detail.error.message,
      }),
    ]);
  }

  if (failing?.status === "failed") {
    const items = [
      evidence("step", `Error raised in ${stepLabel(failing)}`, {
        ref_id: failing.id,
        field: "error.message",
        observed: failing.error!.message,
        excerpt: failing.error!.message,
      }),
    ];
    if (failing.error!.stacktrace) {
      items.push(
        evidence("step", `End of the stack trace of ${stepLabel(failing)}`, {
          ref_id: failing.id,
          field: "error.stacktrace",
          observed: failing.error!.type,
          excerpt: failing.error!.stacktrace.slice(-500),
        }),
      );
    }
    add("failing_step", `${stepLabel(failing)} failed with ${errorText(failing.error)}.`, items);
  } else if (failing) {
    add("failing_step", `${stepLabel(failing)} had started and was still running when the execution timed out.`, [
      evidence("step", `Status of ${stepLabel(failing)}`, { ref_id: failing.id, field: "status", observed: "running" }),
    ]);
  }

  // Outputs just before the failure (or before the end), plus the nearest tool output further back.
  const anchor = failing ? failing.ordinal : detail.step_count + 1;
  const before = steps.filter((s) => s.ordinal < anchor);
  let window = before.slice(-3);
  const nearestTool = [...before].reverse().find((s) => s.tool_name && s.status === "completed");
  if (nearestTool && !window.includes(nearestTool)) window = [nearestTool, ...window];
  for (const step of window) {
    const [description, observed] = describeOutput(step.output);
    add(`output:${step.ordinal}`, `${stepLabel(step)} (${step.type}, ${step.status}) ${description}.`, [
      evidence("step", `Output of ${stepLabel(step)}`, {
        ref_id: step.id,
        field: "output",
        observed,
        excerpt: step.output === null ? null : excerptOf(step.output),
      }),
    ]);
  }

  for (const name of [...new Set(steps.filter((s) => s.attempt > 1).map((s) => s.name))]) {
    const attempts = steps.filter((s) => s.name === name);
    const history = attempts
      .map((s) => `attempt ${s.attempt} ${s.status}${s.error ? ` (${s.error.type})` : ""}`)
      .join(", ");
    add(
      `retry:${name}`,
      `${name} was attempted ${attempts.length} times: ${history}.`,
      attempts.map((s) =>
        evidence("step", `${stepLabel(s)}: ${s.status}`, {
          ref_id: s.id,
          field: s.error ? "error.message" : "status",
          observed: s.error ? s.error.message : s.status,
          excerpt: s.error ? s.error.message : null,
        }),
      ),
    );
  }

  for (const step of steps) {
    const status = httpStatusOf(step);
    if (status === null) continue;
    set.httpStatuses.set(step.id, status);
    const fromOutput =
      isObject(step.output) && ["status", "status_code", "http_status"].some((key) => (step.output as { [k: string]: Json })[key] === status);
    add(`http:${step.ordinal}`, `${stepLabel(step)} (tool ${step.tool_name}) reported HTTP status ${status}.`, [
      evidence("step", `HTTP status reported by ${stepLabel(step)}`, {
        ref_id: step.id,
        field: fromOutput ? "output" : "error.message",
        observed: status,
        expected: "below 400",
        excerpt: fromOutput ? excerptOf(step.output) : step.error!.message,
      }),
    ]);
  }

  const running = steps.filter((s) => s.status === "running" && s !== failing);
  if (running.length) {
    add(
      "running_steps",
      `${running.length} step(s) were still running when the execution ended: ${running.map(stepLabel).join(", ")}.`,
      running.map((s) => evidence("step", `Status of ${stepLabel(s)}`, { ref_id: s.id, field: "status", observed: "running" })),
    );
  }

  const expectedSteps = detail.config.expected_steps ?? [];
  if (expectedSteps.length) {
    const completed = [...new Set(steps.filter((s) => s.status === "completed").map((s) => s.name))];
    const missing = [...new Set(expectedSteps)].filter((name) => !completed.includes(name));
    add(
      "expected_steps",
      `The execution is configured to expect these steps to complete: ${expectedSteps.join(", ")}. ` +
        `Steps that completed: ${completed.join(", ") || "none"}. ` +
        `Expected steps that did not complete: ${missing.join(", ") || "none"}.`,
      [
        evidence("execution", "Expected steps compared with completed steps", {
          ref_id: detail.id,
          field: "config.expected_steps",
          observed: completed,
          expected: expectedSteps,
        }),
      ],
    );
  }

  for (const anomaly of anomalies) {
    add(
      `anomaly:${anomaly.type}`,
      `Anomaly ${anomaly.type} (${anomaly.severity}) was raised on this execution: ${anomaly.title}.`,
      [
        evidence("anomaly", `Why rule ${anomaly.rule_id} fired`, {
          ref_id: anomaly.id,
          field: "explanation",
          observed: anomaly.title,
          excerpt: anomaly.explanation,
        }),
        ...anomaly.evidence,
      ],
    );
  }

  const baseline = baselineFor(view, all);
  if (baseline.runs >= 5) {
    const durationMedian = median(baseline.durations);
    const durationP95 = p95(baseline.durations);
    add(
      "baseline",
      `This execution took ${detail.duration_ms} ms over ${detail.step_count} steps. Over the last ` +
        `${baseline.runs} completed runs of ${run.agent.slug}, the median duration is ${durationMedian} ms ` +
        `(p95 ${durationP95} ms) and the largest step count is ${baseline.maxStepCount}.`,
      [
        evidence("baseline", `This execution compared with ${baseline.runs} completed runs`, {
          observed: {
            duration_ms: detail.duration_ms,
            step_count: detail.step_count,
            tokens_total: detail.tokens_total,
          },
          expected: {
            median_duration_ms: durationMedian,
            p95_duration_ms: durationP95,
            max_step_count: baseline.maxStepCount,
            median_tokens_total: baseline.tokens.length >= 5 ? median(baseline.tokens) : null,
          },
        }),
      ],
    );
  } else {
    set.gaps.push(
      `Only ${baseline.runs} completed baseline run(s) exist for ${run.agent.slug}; at least 5 are needed to ` +
        "compare this execution with normal behaviour.",
    );
  }

  if (detail.status === "failed" && !failing) {
    set.gaps.push("No step recorded the failure, so it happened outside any instrumented step.");
  }
  if (steps.some((s) => isTruncated(s.output))) {
    set.gaps.push("At least one step output was larger than 64 KB and is stored only as a preview.");
  }
  return set;
}

interface SignatureMatch {
  signature: string;
  statement: string;
  reasoning: string;
  supporting: string[];
  stepIds: ID[];
  action: string;
  rationale: string;
}

/** Python's repr() of the key a KeyError names: 'results'. */
const pyRepr = (key: string): string => `'${key}'`;

function matchSignatures(view: RunView, facts: FactSet, anomalies: Anomaly[]): SignatureMatch[] {
  const { detail, steps } = view;
  const failing = facts.failing;
  const cite = (...keys: string[]) => keys.flatMap((key) => facts.ids.get(key) ?? []);
  const matches: SignatureMatch[] = [];

  // missing_key_in_upstream_output
  if (failing?.status === "failed" && failing.error?.type === "KeyError") {
    const key = /^'(.*)'$/.exec(failing.error.message)?.[1];
    const upstream = steps.filter((s) => s.ordinal < failing.ordinal && s.tool_name && s.status === "completed").at(-1);
    if (key !== undefined && upstream && isObject(upstream.output) && !isTruncated(upstream.output) && !(key in upstream.output)) {
      const keys = Object.keys(upstream.output).sort().join(", ") || "(none)";
      matches.push({
        signature: "missing_key_in_upstream_output",
        statement:
          `${stepLabel(failing)} read the key ${pyRepr(key)}, which the output of ${stepLabel(upstream)} ` +
          `(tool ${upstream.tool_name}) does not contain. That output's keys are: ${keys}.`,
        reasoning:
          `Signature missing_key_in_upstream_output: the failing step raised KeyError for ${pyRepr(key)} and the ` +
          `nearest preceding tool output has no key ${pyRepr(key)}. Both conditions are read directly from the ` +
          "recorded step error and the recorded tool output.",
        supporting: cite("failing_step", `output:${upstream.ordinal}`),
        stepIds: [upstream.id, failing.id],
        action:
          `Make ${failing.name} handle the response shape ${upstream.tool_name} now returns (keys: ${keys}), ` +
          `or pin the response format of ${upstream.tool_name}.`,
        rationale: `${failing.name} indexes the key ${pyRepr(key)} directly, and the tool's output no longer has it.`,
      });
    }
  }

  // retry_exhaustion
  if (failing?.status === "failed" && failing.attempt >= 2 && detail.status === "failed") {
    const attempts = steps.filter((s) => s.name === failing.name);
    if (attempts.at(-1) === failing && !attempts.some((s) => s.status === "completed")) {
      matches.push({
        signature: "retry_exhaustion",
        statement:
          `${failing.name} failed on all ${attempts.length} attempts; the last one (${stepLabel(failing)}) failed ` +
          `with ${errorText(failing.error)}, and the execution failed.`,
        reasoning:
          "Signature retry_exhaustion: the step was retried, no attempt completed, and the final attempt " +
          `(attempt ${failing.attempt}) failed. The attempt history is read from the recorded steps.`,
        supporting: cite(`retry:${failing.name}`, "failing_step"),
        stepIds: attempts.map((s) => s.id),
        action: `Find out why ${failing.name} keeps failing before raising its retry budget; add backoff between attempts.`,
        rationale: `Every one of the ${attempts.length} attempts failed, so retrying alone did not help.`,
      });
    }
  }

  // tool_http_error
  if (failing?.status === "failed" && detail.status === "failed") {
    const toolStep = steps.filter((s) => s.tool_name && s.ordinal <= failing.ordinal).at(-1);
    const status = toolStep && facts.httpStatuses.get(toolStep.id);
    if (toolStep && status !== undefined) {
      matches.push({
        signature: "tool_http_error",
        statement:
          toolStep === failing
            ? `${stepLabel(toolStep)} (tool ${toolStep.tool_name}) failed with HTTP status ${status}.`
            : `${stepLabel(toolStep)} (tool ${toolStep.tool_name}) reported HTTP status ${status}, and the ` +
              `later ${stepLabel(failing)} then failed with ${errorText(failing.error)}.`,
        reasoning:
          "Signature tool_http_error: the last tool call up to the failing step recorded an HTTP status of " +
          "400 or above in its output or error, and that step or a step after it failed the execution.",
        supporting: cite(`http:${toolStep.ordinal}`, "failing_step"),
        stepIds: [...new Set([toolStep.id, failing.id])],
        action:
          `Handle HTTP ${status} from ${toolStep.tool_name} explicitly: retry with backoff if it is transient, ` +
          "otherwise stop with a clear error before later steps run on a bad response.",
        rationale: `The run continued or failed on an HTTP ${status} response from ${toolStep.tool_name}.`,
      });
    }
  }

  // timeout_in_step
  if (detail.status === "timed_out" && failing?.status === "running") {
    matches.push({
      signature: "timeout_in_step",
      statement: `The execution timed out while ${stepLabel(failing)} was running; that step never finished.`,
      reasoning:
        "Signature timeout_in_step: the execution's status is timed_out and a step that had started " +
        "has no completion or failure event.",
      supporting: cite("failing_step", "anomaly:stale_execution"),
      stepIds: [failing.id],
      action: `Put a timeout around ${failing.name} and have it fail with an error instead of hanging.`,
      rationale: `${failing.name} is where the run stopped making progress.`,
    });
  }

  // ghost_completion
  const ghost = anomalies.find((a) => a.type === "ghost_completion");
  if (ghost) {
    matches.push({
      signature: "ghost_completion",
      statement: `The agent reported the run as completed, but the recorded steps contradict it: ${ghost.title}.`,
      reasoning:
        "Signature ghost_completion: the execution's status is completed and the deterministic " +
        "ghost_completion rule fired (a step still running, an expected step with no completed step, " +
        "or no steps at all).",
      supporting: cite("anomaly:ghost_completion", "expected_steps", "running_steps"),
      stepIds: [...new Set(ghost.evidence.flatMap((item) => (item.kind === "step" && item.ref_id ? [item.ref_id] : [])))],
      action:
        "Make the agent fail the run when a required step does not complete, instead of reporting success; " +
        "check for errors that are caught and ignored before the missing step.",
      rationale:
        "The run's reported outcome and its recorded steps disagree, so the reported outcome is not trustworthy.",
    });
  }
  return matches;
}

/** What the LLM provider contributed, written by hand in story.ts. Fact references use FactSet keys. */
export interface LlmContribution {
  model: string;
  hypotheses: {
    statement: string;
    confidence: Confidence;
    reasoning: string;
    supports: string[];
    contradicts?: string[];
    /** Ordinals of the steps this hypothesis is about. */
    steps?: number[];
  }[];
  recommendations: { action: string; rationale: string; hypothesis: number | null }[];
  /** Index into `hypotheses` of the proposed root cause. */
  root: number;
  gaps: string[];
}

const NO_ROOT_CAUSE =
  "No deterministic signature matched this execution and no supported hypothesis is available, so the " +
  "recorded evidence is not sufficient to name a root cause.";

export function buildReport(
  view: RunView,
  anomalies: Anomaly[],
  all: RunView[],
  llm: LlmContribution | null,
): InvestigationReport {
  const { detail, steps } = view;
  const facts = buildFacts(view, anomalies, all);
  const matches = matchSignatures(view, facts, anomalies);
  const hypotheses: Hypothesis[] = matches.map((match, index) => ({
    id: `H${index + 1}`,
    statement: match.statement,
    confidence: "high",
    reasoning: match.reasoning,
    supporting_fact_ids: match.supporting,
    contradicting_fact_ids: [],
  }));
  const recommendations: Omit<Recommendation, "id">[] = matches.map((match, index) => ({
    action: match.action,
    rationale: match.rationale,
    hypothesis_id: `H${index + 1}`,
  }));
  const stepIds = matches.flatMap((match) => match.stepIds);
  const gaps = [...facts.gaps];

  let proposedRoot: string | null = null;
  if (llm) {
    const factId = (key: string): string => {
      const id = facts.ids.get(key);
      if (!id) throw new Error(`${view.run.key}: LLM hypothesis cites unknown fact key "${key}"`);
      return id;
    };
    const llmIds = llm.hypotheses.map((_, index) => `H${matches.length + index + 1}`);
    llm.hypotheses.forEach((h, index) => {
      hypotheses.push({
        id: llmIds[index],
        statement: h.statement,
        confidence: h.confidence,
        reasoning: h.reasoning,
        supporting_fact_ids: h.supports.map(factId),
        contradicting_fact_ids: (h.contradicts ?? []).map(factId),
      });
      stepIds.push(...(h.steps ?? []).map((ordinal) => steps[ordinal - 1].id));
    });
    for (const r of llm.recommendations) {
      recommendations.push({
        action: r.action,
        rationale: r.rationale,
        hypothesis_id: r.hypothesis === null ? null : llmIds[r.hypothesis],
      });
    }
    gaps.push(...llm.gaps);
    proposedRoot = llmIds[llm.root];
  }

  const root_cause: RootCause = matches.length
    ? { status: "confirmed", statement: matches[0].statement, hypothesis_id: "H1", signature: matches[0].signature }
    : proposedRoot
      ? {
          status: "probable",
          statement: hypotheses.find((h) => h.id === proposedRoot)!.statement,
          hypothesis_id: proposedRoot,
          signature: null,
        }
      : { status: "insufficient_evidence", statement: NO_ROOT_CAUSE, hypothesis_id: null, signature: null };

  const failing = facts.failing;
  let what: string;
  if (detail.status === "failed" && failing) {
    what = `The execution failed at ${stepLabel(failing)} with ${errorText(failing.error)}.`;
  } else if (detail.status === "failed") {
    what = `The execution failed with ${errorText(detail.error)}; no step recorded the failure.`;
  } else if (detail.status === "timed_out" && failing) {
    what = `The execution timed out while ${stepLabel(failing)} was running.`;
  } else if (detail.status === "timed_out") {
    what = "The execution timed out; no step was running at the time.";
  } else {
    what = `The execution ${detail.status}. Anomalies raised on it: ${anomalies.map((a) => a.type).join(", ") || "none"}.`;
  }
  const verdict = {
    confirmed: `The root cause is confirmed by the deterministic signature ${root_cause.signature}.`,
    probable: "The root cause given is a hypothesis; it is not confirmed.",
    insufficient_evidence: "The recorded evidence is not sufficient to determine a root cause.",
  }[root_cause.status];

  if (failing) stepIds.unshift(failing.id);
  const ordinalOf = new Map(steps.map((s) => [s.id, s.ordinal]));
  return {
    summary: `${what} ${verdict}`,
    failing_step_id: failing?.id ?? null,
    root_cause,
    facts: facts.facts,
    hypotheses,
    recommendations: recommendations.map((r, index) => ({ id: `R${index + 1}`, ...r })),
    evidence_gaps: gaps,
    relevant_step_ids: [...new Set(stepIds)]
      .filter((id) => ordinalOf.has(id))
      .sort((a, b) => ordinalOf.get(a)! - ordinalOf.get(b)!),
  };
}
