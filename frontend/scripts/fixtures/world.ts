/**
 * Building blocks for the fixture world: ids, the fixture clock, a run recorder, and the derivation
 * of events, steps and execution rows from a recorded run.
 *
 * A run is described the way the SDK would record it (steps with timings, then a terminal event).
 * Events are produced first and everything else is derived from the same description, so a trace,
 * its raw events and its execution row can never disagree.
 */
import type {
  ErrorInfo,
  ExecutionConfig,
  ExecutionDetail,
  ExecutionSummary,
  ID,
  Json,
  LogLevel,
  Step,
  StepType,
  StoredEvent,
  Timestamp,
} from "../../lib/api/types";

/** The moment the fixture world is observed at. Every fixture is consistent with this instant. */
export const NOW = Date.parse("2026-11-14T18:00:00.000Z");
export const SECOND = 1000;
export const MINUTE = 60 * SECOND;
export const HOUR = 60 * MINUTE;
export const DAY = 24 * HOUR;

export const iso = (ms: number): Timestamp => new Date(ms).toISOString();
export const at = (text: string): number => Date.parse(text);

type IdPrefix = "agt" | "exe" | "stp" | "evt" | "anm" | "inv" | "rpl";
export const makeId = (prefix: IdPrefix, n: number): ID => `${prefix}_${n.toString(16).padStart(32, "0")}`;

/** Deterministic pseudo-random numbers, so regenerating the fixtures changes nothing. */
export function rng(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Price per million tokens (input, output) used to fill `cost_usd`. Fixture values only: the
 * backend's pricing table (B14) is not built yet. Models missing here get `cost_usd: null`.
 */
const FIXTURE_PRICES: Record<string, [number, number]> = { "claude-haiku-5-5": [1, 5] };

export interface AgentSpec {
  n: number;
  slug: string;
  name: string;
  description: string | null;
  framework: string | null;
  metadata: { [k: string]: Json };
  createdAt: number;
  config: ExecutionConfig;
}

export interface StepSpec {
  ordinal: number;
  name: string;
  type: StepType;
  /** Milliseconds after the execution started. */
  start: number;
  /** Null: the step never ended (still running). */
  duration: number | null;
  parent: number | null;
  input: Json;
  output: Json;
  error: ErrorInfo | null;
  tool_name: string | null;
  model: string | null;
  tokens: [number, number] | null;
  attempt: number;
  startMetadata: { [k: string]: Json };
  endMetadata: { [k: string]: Json };
}

interface LogSpec {
  at: number;
  level: LogLevel;
  message: string;
  step: number | null;
}

type RunEnd =
  | { status: "completed"; at: number; output: Json }
  | { status: "failed"; at: number; error: ErrorInfo }
  | { status: "timed_out"; at: number; lastEventAt: number };

interface StepInput {
  name: string;
  type: StepType;
  /** Duration in ms; null leaves the step running. */
  ms: number | null;
  input?: Json;
  output?: Json;
  error?: ErrorInfo;
  /** A tool call: `tool_name` is the step name and `side_effects` is recorded as metadata. */
  tool?: boolean;
  sideEffects?: boolean;
  model?: string | null;
  tokens?: [number, number];
  attempt?: number;
  parent?: number;
  metadata?: { [k: string]: Json };
}

export class Run {
  readonly id: ID;
  readonly steps: StepSpec[] = [];
  readonly logs: LogSpec[] = [];
  end: RunEnd | null = null;
  replayOf: Run | null = null;
  replayN: number | null = null;
  private cursor = 0;

  constructor(
    readonly n: number,
    readonly key: string,
    readonly agent: AgentSpec,
    readonly startedAt: number,
    readonly input: Json,
    /** One line for the fixture index: what this run represents. */
    readonly note: string,
    readonly config: ExecutionConfig = agent.config,
    readonly tags: string[] = ["demo"],
  ) {
    this.id = makeId("exe", n);
  }

  stepId(ordinal: number): ID {
    return makeId("stp", this.n * 0x100 + ordinal);
  }

  /** Record a step starting 1 ms after the previous one ended. Returns its ordinal. */
  step(s: StepInput): number {
    const ordinal = this.steps.length + 1;
    const start = this.cursor + 1;
    this.steps.push({
      ordinal,
      name: s.name,
      type: s.type,
      start,
      duration: s.ms,
      parent: s.parent ?? null,
      input: s.input ?? null,
      output: s.output ?? null,
      error: s.error ?? null,
      tool_name: s.tool ? s.name : null,
      model: s.model ?? null,
      tokens: s.tokens ?? null,
      attempt: s.attempt ?? 1,
      startMetadata: { ...(s.tool ? { side_effects: s.sideEffects ?? false } : {}), ...s.metadata },
      endMetadata: {},
    });
    this.cursor = start + (s.ms ?? 0);
    return ordinal;
  }

  /** Start a parent step whose children follow; `close` ends it. */
  open(s: Omit<StepInput, "ms">): number {
    const ordinal = this.step({ ...s, ms: null });
    this.cursor = this.steps[ordinal - 1].start;
    return ordinal;
  }

  close(ordinal: number, output: Json): void {
    const step = this.steps[ordinal - 1];
    step.duration = this.cursor + 1 - step.start;
    step.output = output;
    this.cursor += 1;
  }

  wait(ms: number): void {
    this.cursor += ms;
  }

  /** Record a log line `msBack` ms before the current point in the run. */
  log(level: LogLevel, message: string, step: number | null = null, msBack = 0): void {
    this.logs.push({ at: this.cursor - msBack, level, message, step });
  }

  complete(output: Json): this {
    this.end = { status: "completed", at: this.cursor + 1, output };
    return this;
  }

  fail(error: ErrorInfo): this {
    this.end = { status: "failed", at: this.cursor + 1, error };
    return this;
  }

  /** The agent went silent; the sweeper marked the run timed out `idleMs` after its last event. */
  timeOut(idleMs: number): this {
    this.end = { status: "timed_out", at: this.cursor + idleMs, lastEventAt: this.cursor };
    return this;
  }

  asReplayOf(original: Run, replayN: number): this {
    this.replayOf = original;
    this.replayN = replayN;
    return this;
  }

  get status(): ExecutionDetail["status"] {
    return this.end?.status ?? "running";
  }
}

// ── Derivations ─────────────────────────────────────────────────────────────

export function deriveSteps(run: Run): Step[] {
  const depthOf = (spec: StepSpec): number =>
    spec.parent === null ? 0 : 1 + depthOf(run.steps[spec.parent - 1]);
  return run.steps.map((spec) => ({
    id: run.stepId(spec.ordinal),
    execution_id: run.id,
    parent_step_id: spec.parent === null ? null : run.stepId(spec.parent),
    ordinal: spec.ordinal,
    depth: depthOf(spec),
    name: spec.name,
    type: spec.type,
    status: spec.duration === null ? "running" : spec.error ? "failed" : "completed",
    started_at: iso(run.startedAt + spec.start),
    ended_at: spec.duration === null ? null : iso(run.startedAt + spec.start + spec.duration),
    duration_ms: spec.duration,
    offset_ms: spec.start,
    input: spec.input,
    output: spec.output,
    error: spec.error,
    tool_name: spec.tool_name,
    model: spec.model,
    tokens_input: spec.tokens?.[0] ?? null,
    tokens_output: spec.tokens?.[1] ?? null,
    attempt: spec.attempt,
    metadata: { ...spec.startMetadata, ...spec.endMetadata },
  }));
}

/** The SDK flushes every 500 ms, so events arrive in batches a little after they happened. */
const receivedAt = (run: Run, offset: number): number =>
  run.startedAt + Math.ceil((offset + 1) / 500) * 500 + 9;

export function deriveEvents(run: Run): StoredEvent[] {
  type Draft = Pick<StoredEvent, "type" | "payload"> & { at: number; order: number; received?: number };
  const drafts: Draft[] = [];
  let order = 0;
  for (const spec of run.steps) {
    const step_id = run.stepId(spec.ordinal);
    drafts.push({
      at: spec.start,
      order: order++,
      type: "step.started",
      payload: {
        step_id,
        parent_step_id: spec.parent === null ? null : run.stepId(spec.parent),
        name: spec.name,
        step_type: spec.type,
        input: spec.input,
        tool_name: spec.tool_name,
        model: spec.model,
        attempt: spec.attempt,
        metadata: spec.startMetadata,
      },
    });
    if (spec.duration === null) continue;
    drafts.push(
      spec.error
        ? {
            at: spec.start + spec.duration,
            order: order++,
            type: "step.failed",
            payload: { step_id, error: { ...spec.error }, output: spec.output },
          }
        : {
            at: spec.start + spec.duration,
            order: order++,
            type: "step.completed",
            payload: {
              step_id,
              output: spec.output,
              tokens_input: spec.tokens?.[0] ?? null,
              tokens_output: spec.tokens?.[1] ?? null,
              metadata: spec.endMetadata,
            },
          },
    );
  }
  for (const log of run.logs) {
    drafts.push({
      at: log.at,
      order: order++,
      type: "log",
      payload: {
        level: log.level,
        message: log.message,
        step_id: log.step === null ? null : run.stepId(log.step),
      },
    });
  }
  if (run.end?.status === "completed") {
    drafts.push({ at: run.end.at, order: order++, type: "execution.completed", payload: { output: run.end.output } });
  } else if (run.end?.status === "failed") {
    drafts.push({ at: run.end.at, order: order++, type: "execution.failed", payload: { error: { ...run.end.error } } });
  } else if (run.end?.status === "timed_out") {
    // Appended by the backend's sweeper, not sent by the agent: received the moment it was written.
    drafts.push({
      at: run.end.at,
      order: order++,
      type: "execution.timed_out",
      payload: {},
      received: run.startedAt + run.end.at,
    });
  }
  drafts.sort((a, b) => a.at - b.at || a.order - b.order);
  return drafts.map((draft, index) => ({
    id: makeId("evt", run.n * 0x1000 + index + 1),
    seq: index + 1,
    type: draft.type,
    timestamp: iso(run.startedAt + draft.at),
    received_at: iso(draft.received ?? receivedAt(run, draft.at)),
    payload: draft.payload,
  }));
}

function costOf(run: Run): number | null {
  let cost: number | null = null;
  for (const spec of run.steps) {
    const price = spec.model ? FIXTURE_PRICES[spec.model] : undefined;
    if (!price || !spec.tokens) continue;
    cost = (cost ?? 0) + (spec.tokens[0] * price[0] + spec.tokens[1] * price[1]) / 1_000_000;
  }
  return cost === null ? null : Math.round(cost * 1_000_000) / 1_000_000;
}

export interface ExecutionLinks {
  anomalyCount: number;
  hasInvestigation: boolean;
  replayIds: ID[];
}

export function deriveDetail(run: Run, links: ExecutionLinks): ExecutionDetail {
  const reported = run.steps.filter((spec) => spec.tokens !== null);
  const tokensInput = reported.length ? reported.reduce((sum, spec) => sum + spec.tokens![0], 0) : null;
  const tokensOutput = reported.length ? reported.reduce((sum, spec) => sum + spec.tokens![1], 0) : null;
  const end = run.end;
  const error: ErrorInfo | null =
    end?.status === "failed"
      ? end.error
      : end?.status === "timed_out"
        ? { type: "TimeoutError", message: `Execution timed out after ${end.at} ms.`, stacktrace: null }
        : null;
  return {
    id: run.id,
    agent_id: makeId("agt", run.agent.n),
    agent_name: run.agent.name,
    status: run.status,
    started_at: iso(run.startedAt),
    ended_at: end ? iso(run.startedAt + end.at) : null,
    duration_ms: end ? end.at : null,
    step_count: run.steps.length,
    tokens_total: tokensInput === null || tokensOutput === null ? null : tokensInput + tokensOutput,
    cost_usd: costOf(run),
    anomaly_count: links.anomalyCount,
    has_investigation: links.hasInvestigation,
    replay_of: run.replayOf?.id ?? null,
    error,
    input: run.input,
    output: end?.status === "completed" ? end.output : null,
    config: run.config,
    tokens_input: tokensInput,
    tokens_output: tokensOutput,
    tags: run.tags,
    replay_ids: links.replayIds,
  };
}

export function toSummary(detail: ExecutionDetail): ExecutionSummary {
  return {
    id: detail.id,
    agent_id: detail.agent_id,
    agent_name: detail.agent_name,
    status: detail.status,
    started_at: detail.started_at,
    ended_at: detail.ended_at,
    duration_ms: detail.duration_ms,
    step_count: detail.step_count,
    tokens_total: detail.tokens_total,
    cost_usd: detail.cost_usd,
    anomaly_count: detail.anomaly_count,
    has_investigation: detail.has_investigation,
    replay_of: detail.replay_of,
    error: detail.error,
  };
}

/** A Python traceback as the SDK records it (`traceback.format_exception`). */
export function pythonError(type: string, message: string, frames: [file: string, line: number, fn: string, code: string][]): ErrorInfo {
  const body = frames
    .map(([file, line, fn, code]) => `  File "${file}", line ${line}, in ${fn}\n    ${code}\n`)
    .join("");
  return { type, message, stacktrace: `Traceback (most recent call last):\n${body}${type}: ${message}\n` };
}
