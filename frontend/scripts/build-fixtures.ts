/**
 * Writes contract/fixtures/ from the fixture story (scripts/fixtures/story.ts).
 *
 *   npm run build-fixtures
 *
 * The JSON files in contract/fixtures/ are the canonical fixtures; this script is how they were
 * authored and how a contract change regenerates them. It is deterministic: running it twice
 * produces identical files. After the X1 PR merges, fixtures change only through the
 * contract-change process (CONTRIBUTING.md), so do not run it outside a `contract/<topic>` branch.
 */
import { mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import type {
  Agent,
  AgentHealth,
  Anomaly,
  ErrorCode,
  ErrorEnvelope,
  ExecutionDetail,
  Health,
  IngestResponse,
  Investigation,
  Json,
  Page,
  RecordedCall,
  Replay,
  ReplayClaim,
  ReplayComparison,
  ReplayOutcome,
  StatsBucket,
  StatsOverview,
  StatsTimeseries,
  StatsWindow,
  Step,
  StepDiff,
  StoredEvent,
  Trace,
} from "../lib/api/types";
import { detect, evidence, toAnomaly, type RunView } from "./fixtures/anomalies";
import { buildReport } from "./fixtures/investigation";
import {
  agents,
  anomalyStatus,
  fetchFailed,
  ghostInvoice,
  healthy,
  investigationFailures,
  llmContributions,
  rateLimit,
  replays,
  research,
  running,
  runs,
  schemaChange,
  slow,
  timedOut,
  timedOutFirst,
  type ReplaySpec,
} from "./fixtures/story";
import { DAY, deriveDetail, deriveEvents, deriveSteps, HOUR, iso, makeId, NOW, Run, toSummary, type AgentSpec } from "./fixtures/world";

const OUT_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "../../contract/fixtures");

// ── Executions, steps, events ───────────────────────────────────────────────

const views: RunView[] = runs.map((run) => ({
  run,
  steps: deriveSteps(run),
  detail: deriveDetail(run, { anomalyCount: 0, hasInvestigation: false, replayIds: [] }),
}));
const viewOf = (run: Run): RunView => views.find((view) => view.run === run)!;
const eventsOf = new Map(runs.map((run) => [run, deriveEvents(run)]));
const endedAt = (view: RunView): number => view.run.startedAt + view.run.end!.at;
const ended = views.filter((view) => view.run.end).sort((a, b) => endedAt(a) - endedAt(b));

// ── Anomalies: the rules run on every execution as it ends ──────────────────

const anomaliesOf = new Map<Run, Anomaly[]>(runs.map((run) => [run, []]));
let anomalyCount = 0;
for (const view of ended) {
  anomaliesOf.set(
    view.run,
    detect(view, views).map((draft) =>
      toAnomaly(view, draft, makeId("anm", ++anomalyCount), anomalyStatus[`${view.run.key}:${draft.type}`] ?? "open"),
    ),
  );
}
const anomalyOf = (run: Run, type: Anomaly["type"]): Anomaly => {
  const found = anomaliesOf.get(run)!.find((anomaly) => anomaly.type === type);
  if (!found) throw new Error(`Expected ${type} on ${run.key}; the story no longer triggers it.`);
  return found;
};

// The backend's v1 rules emit evidence of kind step, execution, baseline and anomaly only. These two
// items add the remaining kinds (event, metric) so the UI's treatment of them has a fixture.
{
  const log = eventsOf.get(ghostInvoice)!.find((event) => event.type === "log")!;
  anomalyOf(ghostInvoice, "ghost_completion").evidence.push(
    evidence("event", `Warning logged at event ${log.seq}`, {
      ref_id: log.id,
      field: "payload.message",
      observed: log.payload.message,
      excerpt: String(log.payload.message),
    }),
  );
  const kb = viewOf(slow).steps.find((step) => step.name === "retrieve_kb")!;
  anomalyOf(slow, "duration_spike").evidence.push(
    evidence("metric", "Share of the execution spent in retrieve_kb", {
      field: "steps.duration_ms",
      observed: {
        step: kb.name,
        duration_ms: kb.duration_ms,
        share: Math.round((kb.duration_ms! / viewOf(slow).detail.duration_ms!) * 1000) / 1000,
      },
    }),
  );
}

// ── Investigations: queued on failure, timeout, or an anomaly of high or above ──

const investigations: Investigation[] = [];
let investigationCount = 0;
for (const view of ended) {
  const anomalies = anomaliesOf.get(view.run)!;
  const failed = view.detail.status === "failed" || view.detail.status === "timed_out";
  if (!failed && !anomalies.some((a) => a.severity === "high" || a.severity === "critical")) continue;
  const created = endedAt(view) + 38;
  const failure = investigationFailures[view.run.key];
  const llm = llmContributions[view.run.key] ?? null;
  const base = {
    id: makeId("inv", ++investigationCount),
    execution_id: view.detail.id,
    trigger: failed ? "auto_failure" : "auto_anomaly",
    created_at: iso(created),
  } as const;
  investigations.push(
    failure
      ? { ...base, status: "failed", provider: "rule_based", model: null, completed_at: iso(created + 212), error: failure, report: null }
      : {
          ...base,
          status: "completed",
          provider: llm ? "fable" : "rule_based",
          model: llm?.model ?? null,
          completed_at: iso(created + (llm ? 9_420 : 164)),
          error: null,
          report: buildReport(view, anomalies, views, llm),
        },
  );
}
const investigationOf = (run: Run): Investigation => {
  const found = investigations.find((investigation) => investigation.execution_id === run.id);
  if (!found) throw new Error(`Expected an investigation on ${run.key}.`);
  return found;
};

// A manual investigation of `rate_limit`, in the three states a client polls through. These are
// not in investigations.list.json: in the fixture world nobody has clicked Investigate yet.
const manualQueued: Investigation = {
  id: makeId("inv", ++investigationCount),
  execution_id: rateLimit.id,
  status: "queued",
  trigger: "manual",
  provider: "rule_based",
  model: null,
  created_at: iso(NOW - 310),
  completed_at: null,
  error: null,
  report: null,
};
const manualRunning: Investigation = { ...manualQueued, status: "running" };
const manualResult: Investigation = {
  ...manualQueued,
  status: "completed",
  completed_at: iso(NOW + 1_870),
  report: buildReport(viewOf(rateLimit), anomaliesOf.get(rateLimit)!, views, null),
};

// ── Replays ─────────────────────────────────────────────────────────────────

function outcomeOf(original: RunView, replayed: RunView): ReplayOutcome {
  const [a, b] = [original.detail.status, replayed.detail.status];
  if (a === "failed" && b === "completed") return "fixed";
  if (a === "completed" && b === "failed") return "regressed";
  if (a === "completed" && b === "completed") return "both_succeeded";
  if (a === "failed" && b === "failed") {
    const failing = (view: RunView) => view.steps.filter((step) => step.status === "failed").at(-1);
    const [x, y] = [failing(original), failing(replayed)];
    return x && y && x.name === y.name && x.error?.type === y.error?.type ? "same_failure" : "different_failure";
  }
  return "inconclusive";
}

function compare(original: RunView, replayed: RunView): ReplayComparison {
  const keyOf = (step: Step) => `${step.ordinal}:${step.name}`;
  const before = new Map(original.steps.map((step) => [keyOf(step), step]));
  const after = new Map(replayed.steps.map((step) => [keyOf(step), step]));
  const step_diffs: StepDiff[] = [...new Set([...before.keys(), ...after.keys()])]
    .map((key): StepDiff => {
      const [x, y] = [before.get(key), after.get(key)];
      return {
        ordinal: (x ?? y)!.ordinal,
        name: (x ?? y)!.name,
        original_step_id: x?.id ?? null,
        replay_step_id: y?.id ?? null,
        change: !x
          ? "added"
          : !y
            ? "removed"
            : x.status !== y.status
              ? "status_changed"
              : JSON.stringify(x.output) !== JSON.stringify(y.output)
                ? "output_changed"
                : "unchanged",
        original_status: x?.status ?? null,
        replay_status: y?.status ?? null,
      };
    })
    .sort((p, q) => p.ordinal - q.ordinal || (p.original_step_id ? -1 : 1));
  const delta = (x: number | null, y: number | null) => (x === null || y === null ? null : y - x);
  return {
    original: toSummary(original.detail),
    replay: toSummary(replayed.detail),
    outcome: outcomeOf(original, replayed),
    duration_delta_ms: delta(original.detail.duration_ms, replayed.detail.duration_ms),
    tokens_delta: delta(original.detail.tokens_total, replayed.detail.tokens_total),
    step_count_delta: replayed.detail.step_count - original.detail.step_count,
    step_diffs,
  };
}

/** Built after every execution row is final, because a comparison embeds two of them. */
function toReplay(spec: ReplaySpec): Replay {
  const claimed = spec.claimedAfter === null ? null : spec.requestedAt + spec.claimedAfter;
  const replayed = spec.replay && viewOf(spec.replay);
  return {
    id: makeId("rpl", spec.n),
    original_execution_id: spec.original.id,
    replay_execution_id: spec.replay?.id ?? null,
    mode: spec.mode,
    status: spec.status,
    side_effects_authorized: spec.mode === "live",
    note: spec.note,
    requested_at: iso(spec.requestedAt),
    claimed_at: claimed === null ? null : iso(claimed),
    completed_at: replayed ? iso(endedAt(replayed) + 24) : spec.status === "failed" ? iso(claimed! + 310) : null,
    error: spec.error,
    comparison: replayed ? compare(viewOf(spec.original), replayed) : null,
  };
}

// ── Final execution rows: now the links are known ───────────────────────────

for (const view of views) {
  view.detail.anomaly_count = anomaliesOf.get(view.run)!.length;
  view.detail.has_investigation = investigations.some((investigation) => investigation.execution_id === view.run.id);
  view.detail.replay_ids = replays
    .filter((spec) => spec.original === view.run)
    .sort((a, b) => a.requestedAt - b.requestedAt)
    .map((spec) => makeId("rpl", spec.n));
}
const allReplays = replays.map(toReplay);
const replayOf = (key: string): Replay => allReplays[replays.findIndex((spec) => spec.key === key)];
const allAnomalies = [...anomaliesOf.values()].flat();
const newestFirst = [...views].sort((a, b) => b.run.startedAt - a.run.startedAt);

// ── Agents ──────────────────────────────────────────────────────────────────

function toAgent(spec: AgentSpec): Agent {
  const id = makeId("agt", spec.n);
  const own = newestFirst.filter((view) => view.run.agent === spec);
  const count = (status: ExecutionDetail["status"]) => own.filter((view) => view.detail.status === status).length;
  const terminal = own.filter((view) => view.detail.status !== "running");
  const open = allAnomalies.filter((anomaly) => anomaly.agent_id === id && anomaly.status === "open");
  const recent = terminal.slice(0, 20);
  const recentRate = recent.length ? recent.filter((view) => view.detail.status === "completed").length / recent.length : null;
  const health: AgentHealth =
    own.length === 0
      ? "idle"
      : open.some((a) => a.severity === "critical") || (recentRate !== null && recentRate < 0.5)
        ? "failing"
        : open.some((a) => a.severity === "high") || (recentRate !== null && recentRate < 0.9)
          ? "degraded"
          : "healthy";
  return {
    id,
    name: spec.name,
    slug: spec.slug,
    description: spec.description,
    framework: spec.framework,
    metadata: spec.metadata,
    created_at: iso(spec.createdAt),
    stats: {
      total_executions: own.length,
      completed: count("completed"),
      failed: count("failed"),
      timed_out: count("timed_out"),
      running: count("running"),
      success_rate: terminal.length ? count("completed") / terminal.length : null,
      avg_duration_ms: terminal.length
        ? Math.round(terminal.reduce((sum, view) => sum + view.detail.duration_ms!, 0) / terminal.length)
        : null,
      open_anomalies: open.length,
      last_execution: own.length ? toSummary(own[0].detail) : null,
      health,
    },
  };
}
const allAgents = agents.map(toAgent).sort((a, b) => a.name.localeCompare(b.name));

// ── Stats: a window is whole UTC buckets ending with the current one ────────

const BUCKET_MS: Record<StatsBucket, number> = { hour: HOUR, day: DAY };
const WINDOW_MS: Record<StatsWindow, number> = { "24h": DAY, "7d": 7 * DAY, "30d": 30 * DAY };
const defaultBucket = (window: StatsWindow): StatsBucket => (window === "24h" ? "hour" : "day");

function windowStart(window: StatsWindow, bucket: StatsBucket): number {
  const size = BUCKET_MS[bucket];
  return Math.floor(NOW / size) * size + size - WINDOW_MS[window];
}

const average = (list: RunView[]): number | null =>
  list.length ? Math.round(list.reduce((sum, view) => sum + view.detail.duration_ms!, 0) / list.length) : null;

function overview(window: StatsWindow): StatsOverview {
  const inWindow = views.filter((view) => view.run.startedAt >= windowStart(window, defaultBucket(window)));
  const count = (status: ExecutionDetail["status"]) => inWindow.filter((view) => view.detail.status === status).length;
  const terminal = inWindow.filter((view) => view.detail.status !== "running");
  return {
    window,
    total_agents: agents.length,
    total_executions: inWindow.length,
    completed: count("completed"),
    failed: count("failed"),
    timed_out: count("timed_out"),
    running: count("running"),
    success_rate: terminal.length ? count("completed") / terminal.length : null,
    avg_duration_ms: average(terminal),
    open_anomalies: allAnomalies.filter((anomaly) => anomaly.status === "open").length,
  };
}

function timeseries(window: StatsWindow, bucket: StatsBucket): StatsTimeseries {
  const size = BUCKET_MS[bucket];
  const start = windowStart(window, bucket);
  const points = Array.from({ length: WINDOW_MS[window] / size }, (_, index) => {
    const from = start + index * size;
    const inBucket = views.filter(
      (view) => view.detail.status !== "running" && view.run.startedAt >= from && view.run.startedAt < from + size,
    );
    const count = (status: ExecutionDetail["status"]) => inBucket.filter((view) => view.detail.status === status).length;
    return {
      bucket_start: iso(from),
      completed: count("completed"),
      failed: count("failed"),
      timed_out: count("timed_out"),
      avg_duration_ms: average(inBucket),
    };
  });
  return { window, bucket, points };
}

// ── Assemble the files ──────────────────────────────────────────────────────

const page = <T>(items: T[], limit = 50): Page<T> => ({ items, total: items.length, limit, offset: 0 });
const emptyPage: Page<never> = { items: [], total: 0, limit: 50, offset: 0 };

const traceOf = (view: RunView): Trace => ({
  execution: view.detail,
  steps: view.steps,
  anomalies: anomaliesOf.get(view.run)!,
  event_count: eventsOf.get(view.run)!.length,
});

const errorOf = (code: ErrorCode, message: string, details: Json = null): ErrorEnvelope => ({
  error: { code, message, details },
});
const UNKNOWN_EXECUTION = makeId("exe", 0xdead);

const health: Health = {
  status: "ok",
  version: "0.1.0",
  database: "ok",
  llm_provider: "rule_based",
  llm_configured: true,
  llm_model: null,
};

// What POST /executions answers: a run that has just been created and has recorded nothing yet.
const created = new Run(0x7f, "created", research, NOW - 140, { question: "How does schema drift break API consumers?" }, "");
const ingest: IngestResponse = { accepted: 9, duplicates: 0, execution_status: "completed" };

const claimedOriginal = viewOf(timedOutFirst);
const occurrences = new Map<string, number>();
const claim: ReplayClaim = {
  replay: replayOf("claimed"),
  bundle: {
    original_execution: claimedOriginal.detail,
    recorded_calls: claimedOriginal.steps
      .filter((step) => step.tool_name !== null || step.type === "llm_call")
      .map((step): RecordedCall => {
        const key = `${step.type}:${step.tool_name ?? step.name}`;
        occurrences.set(key, (occurrences.get(key) ?? 0) + 1);
        return {
          step_name: step.name,
          step_type: step.type,
          tool_name: step.tool_name,
          occurrence: occurrences.get(key)!,
          input: step.input,
          output: step.output,
          error: step.error,
        };
      }),
  },
};

const files: Record<string, unknown> = {
  "health.get": health,

  "agents.list": page(allAgents),
  "agents.list.empty": emptyPage,
  "agents.create": allAgents.find((agent) => agent.slug === research.slug),
  ...Object.fromEntries(allAgents.map((agent) => [`agents.get.${agent.slug}`, agent])),

  "executions.list": page(newestFirst.map((view) => toSummary(view.detail)), 200),
  "executions.list.empty": emptyPage,
  "executions.create": deriveDetail(created, { anomalyCount: 0, hasInvestigation: false, replayIds: [] }),
  "executions.ingest": ingest,
  ...Object.fromEntries(
    [healthy, schemaChange, ghostInvoice, running, timedOut].map((run) => [`executions.get.${run.key}`, viewOf(run).detail]),
  ),
  ...Object.fromEntries(views.map((view) => [`executions.trace.${view.run.id}`, traceOf(view)])),
  ...Object.fromEntries(views.map((view) => [`executions.events.${view.run.id}`, page<StoredEvent>(eventsOf.get(view.run)!, 200)])),

  "stats.overview.24h": overview("24h"),
  "stats.overview.7d": overview("7d"),
  "stats.overview.30d": overview("30d"),
  "stats.timeseries.24h.hour": timeseries("24h", "hour"),
  "stats.timeseries.7d.day": timeseries("7d", "day"),
  "stats.timeseries.30d.day": timeseries("30d", "day"),

  "anomalies.list": page([...allAnomalies].sort((a, b) => b.detected_at.localeCompare(a.detected_at))),
  "anomalies.list.empty": emptyPage,
  "anomalies.get.ghost_completion": anomalyOf(ghostInvoice, "ghost_completion"),
  "anomalies.update": allAnomalies.find((anomaly) => anomaly.status === "acknowledged"),

  "investigations.list": page([...investigations].sort((a, b) => b.created_at.localeCompare(a.created_at))),
  "investigations.list.empty": emptyPage,
  "investigations.get.confirmed": investigationOf(schemaChange),
  "investigations.get.probable": investigationOf(runs.find((run) => run.key === "token_spike")!),
  "investigations.get.insufficient_evidence": investigationOf(runs.find((run) => run.key === "replay_different_failure")!),
  "investigations.get.ghost_completion": investigationOf(ghostInvoice),
  "investigations.get.timeout": investigationOf(timedOut),
  "investigations.get.failed": investigationOf(fetchFailed),
  "investigations.create": manualQueued,
  "investigations.get.queued": manualQueued,
  "investigations.get.running": manualRunning,
  "investigations.get.manual_result": manualResult,

  "replays.list": page([...allReplays].sort((a, b) => b.requested_at.localeCompare(a.requested_at))),
  "replays.list.empty": emptyPage,
  "replays.create": replayOf("pending"),
  "replays.claim": claim,
  ...Object.fromEntries(replays.map((spec) => [`replays.get.${spec.key}`, replayOf(spec.key)])),

  "error.bad_request": errorOf("bad_request", "Unknown sort field 'agent'. Allowed: started_at, duration_ms, tokens_total, cost_usd."),
  "error.unauthorized": errorOf("unauthorized", "Missing or invalid API key."),
  "error.not_found": errorOf("not_found", `Execution ${UNKNOWN_EXECUTION} does not exist.`),
  "error.conflict": errorOf("conflict", "An investigation cannot be started while the execution is still running."),
  "error.execution_already_terminal": errorOf(
    "execution_already_terminal",
    `Execution ${schemaChange.id} is already failed; no further events are accepted.`,
  ),
  "error.validation_error": errorOf("validation_error", "Request validation failed.", [
    { loc: ["body", "mode"], msg: "Input should be 'sandbox' or 'live'" },
  ]),
  "error.side_effect_authorization_required": errorOf(
    "side_effect_authorization_required",
    "A live replay runs tools for real. Set authorize_side_effects to true to confirm.",
  ),
  "error.internal_error": errorOf("internal_error", "An internal error occurred."),
  "error.llm_unavailable": errorOf(
    "llm_unavailable",
    "The LLM provider is not available and the rule-based fallback is disabled.",
  ),
};

// ── Sanity checks on the story itself ───────────────────────────────────────

const expectations: [string, unknown, unknown][] = [
  ["schema_change root cause", investigationOf(schemaChange).report?.root_cause.signature, "missing_key_in_upstream_output"],
  ["ghost_invoice root cause", investigationOf(ghostInvoice).report?.root_cause.signature, "ghost_completion"],
  ["timed_out root cause", investigationOf(timedOut).report?.root_cause.signature, "timeout_in_step"],
  ["token_spike root cause", investigationOf(runs.find((run) => run.key === "token_spike")!).report?.root_cause.status, "probable"],
  ["wrong-fix replay root cause", investigationOf(runs.find((run) => run.key === "replay_different_failure")!).report?.root_cause.status, "insufficient_evidence"],
  ["rate_limit has no investigation", viewOf(rateLimit).detail.has_investigation, false],
  ...replays.filter((spec) => spec.replay).map((spec): [string, unknown, unknown] => [`replay ${spec.key} outcome`, replayOf(spec.key).comparison?.outcome, spec.key]),
  ...(["healthy", "degraded", "failing", "idle"] as const).map((value): [string, unknown, unknown] => [
    `an agent is ${value}`,
    allAgents.some((agent) => agent.stats.health === value),
    true,
  ]),
];
const broken = expectations.filter(([, actual, expected]) => actual !== expected);
if (broken.length) {
  for (const [what, actual, expected] of broken) console.error(`✗ ${what}: expected ${String(expected)}, got ${String(actual)}`);
  process.exit(1);
}

// ── Write ───────────────────────────────────────────────────────────────────

mkdirSync(OUT_DIR, { recursive: true });
for (const file of readdirSync(OUT_DIR)) {
  if (file.endsWith(".json") || file === "README.md") rmSync(join(OUT_DIR, file));
}
for (const [name, value] of Object.entries(files)) {
  writeFileSync(join(OUT_DIR, `${name}.json`), `${JSON.stringify(value, null, 2)}\n`);
}

const scenarioRows = views
  .filter((view) => !view.run.note.startsWith("Routine"))
  .map((view) => `| \`${view.run.key}\` | ${view.run.agent.slug} | ${view.detail.status} | \`${view.run.id}\` | ${view.run.note} |`);
const routineRows = agents
  .map((spec) => {
    const own = views.filter((view) => view.run.agent === spec && view.run.note.startsWith("Routine"));
    return own.length ? `- ${spec.slug}: ${own.length} runs, \`${own[0].run.id}\` … \`${own.at(-1)!.run.id}\`` : null;
  })
  .filter(Boolean);
const readme = `# Contract fixtures

Canonical example responses for every endpoint in \`../API_CONTRACT.md\` (v1.1). The frontend's mock
mode serves these files; the backend's conformance tests (B15) validate each one against its schema.

They are one consistent snapshot of a small world, observed at **${iso(NOW)}**: the same ids appear in
every file, so a link in one fixture resolves in another. Change them only through the
contract-change process in \`CONTRIBUTING.md\`.

## Naming

\`<resource>.<operation>[.<variant>].json\`. The \`<resource>.<operation>\` pair selects the schema
(\`backend/tests/fixture_map.py\`); the variant is free text. \`executions.trace.<execution id>.json\`
and \`executions.events.<execution id>.json\` exist for every execution in \`executions.list.json\`.

## Agents

| Slug | Health | Why |
|---|---|---|
${allAgents.map((agent) => `| \`${agent.slug}\` | ${agent.stats.health} | ${agent.stats.total_executions} executions, ${agent.stats.open_anomalies} open anomalies, id \`${agent.id}\` |`).join("\n")}

## Scenario executions

| Key | Agent | Status | Execution id | What it is |
|---|---|---|---|---|
${scenarioRows.join("\n")}

Routine healthy runs that form the baselines:

${routineRows.join("\n")}

## Investigations

| File | Execution | What it shows |
|---|---|---|
| \`investigations.get.confirmed.json\` | \`schema_change\` | Root cause confirmed by signature \`missing_key_in_upstream_output\` |
| \`investigations.get.ghost_completion.json\` | \`ghost_invoice\` | Confirmed by signature \`ghost_completion\`, trigger \`auto_anomaly\` |
| \`investigations.get.timeout.json\` | \`timed_out\` | Confirmed by signature \`timeout_in_step\`; has an evidence gap (too few baseline runs) |
| \`investigations.get.probable.json\` | \`token_spike\` | Provider \`fable\`: two LLM hypotheses, one with a contradicting fact; root cause \`probable\` |
| \`investigations.get.insufficient_evidence.json\` | \`replay_different_failure\` | No signature matched and no hypothesis: \`insufficient_evidence\` |
| \`investigations.get.failed.json\` | \`fetch_failed\` | The investigation itself failed |
| \`investigations.create.json\`, \`.get.queued\`, \`.get.running\`, \`.get.manual_result\` | \`rate_limit\` | One manual investigation in the states a client polls through. Not in \`investigations.list.json\`: in this snapshot nobody has started it |

## Replays

One per outcome (\`replays.get.<outcome>.json\`), plus \`pending\`, \`claimed\` and \`failed\`.
\`replays.get.fixed.json\` is the demo: the sandbox replay of \`schema_change\` after the parser fix.
\`replays.get.both_succeeded.json\` is the only \`live\` replay and is authorized.

## Things that are deliberately here

- \`_truncated\` payload markers: step inputs and outputs and the execution output of \`token_spike\`.
- Nested steps (\`depth\` 1): \`summarize_batch\` under \`summarize\` in the \`ticket-digest\` runs.
- A retried step: \`retrieve_kb\` attempts 1–3 in \`rate_limit\`; \`fetch_tickets\` in \`fetch_failed\`.
- \`cost_usd\` is \`null\` for \`demo-llm-1\` (no pricing) and set for the \`ticket-digest\` runs, using a
  fixture-only price for \`${"claude-haiku-5-5"}\`. The backend's pricing table (B14) is not built yet.
- Evidence of kind \`event\` (on the \`ghost_completion\` anomaly) and \`metric\` (on the \`slow\` run's
  \`duration_spike\`). The backend's v1 rules do not emit these two kinds; they are here so every
  \`EvidenceKind\` has an example.
- Anomaly statuses \`acknowledged\` and \`resolved\`, although \`PATCH /anomalies/{id}\` is P1.
- An empty page for each list endpoint and one file per error code.

## Regenerating

Authored by \`frontend/scripts/build-fixtures.ts\` from \`frontend/scripts/fixtures/story.ts\`; titles,
explanations, facts and signatures follow the backend's rule and report templates. Check with
\`cd frontend && npm run validate-fixtures\`.
`;
writeFileSync(join(OUT_DIR, "README.md"), readme);

console.log(`Wrote ${Object.keys(files).length} fixtures to ${OUT_DIR}`);
console.log(
  `  ${views.length} executions · ${allAnomalies.length} anomalies · ${investigations.length} investigations · ${allReplays.length} replays`,
);
