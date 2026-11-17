/**
 * Checks every file in contract/fixtures/ against lib/api/types.ts and against each other.
 *
 *   npm run validate-fixtures
 *
 * 1. Types. TypeScript types do not exist at runtime, and importing JSON widens enum values to
 *    `string`, so each fixture is inlined as a literal into a generated file as
 *    `(<json>) satisfies <Type>` and compiled with tsc. That catches a missing key, an extra key,
 *    a wrong type and an unknown enum value. Three deliberately broken literals in the same file
 *    must fail, which proves the check can fail.
 * 2. Formats the type system cannot express: ids, timestamps.
 * 3. Consistency across files: every id resolves, lists agree with traces.
 * 4. Coverage: every enum value of the contract appears, plus the special cases the UI must handle.
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  AGENT_HEALTHS,
  ANOMALY_STATUSES,
  ANOMALY_TYPES,
  CONFIDENCES,
  ERROR_CODES,
  EVENT_TYPES,
  EVIDENCE_KINDS,
  EXECUTION_STATUSES,
  INVESTIGATION_PROVIDERS,
  INVESTIGATION_STATUSES,
  INVESTIGATION_TRIGGERS,
  REPLAY_MODES,
  REPLAY_OUTCOMES,
  REPLAY_SOURCES,
  REPLAY_STATUSES,
  ROOT_CAUSE_STATUSES,
  SEVERITIES,
  STEP_CHANGES,
  STEP_STATUSES,
  STEP_TYPES,
} from "../lib/api/types";
import { typeFor } from "./fixture-types";

const FRONTEND = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const FIXTURES = resolve(FRONTEND, "../contract/fixtures");
const CHECK_DIR = join(FRONTEND, ".fixture-check");

type Node = null | boolean | number | string | Node[] | { [k: string]: Node };
const isRecord = (node: Node): node is { [k: string]: Node } => typeof node === "object" && node !== null && !Array.isArray(node);

const problems: string[] = [];
const fail = (message: string) => problems.push(message);

const names = readdirSync(FIXTURES).filter((file) => file.endsWith(".json")).sort();
if (names.length === 0) {
  console.error(`No fixtures found in ${FIXTURES}`);
  process.exit(1);
}
const docs = new Map<string, Node>(names.map((file) => [file, JSON.parse(readFileSync(join(FIXTURES, file), "utf8")) as Node]));

// ── 1. Types ────────────────────────────────────────────────────────────────

const lines = ['import type * as T from "../lib/api/types";', ""];
names.forEach((file, index) => {
  const type = typeFor(file);
  if (!type) return fail(`${file}: no type is mapped to this name; rename it or add its operation to TYPES`);
  lines.push(`// ${file}`, `export const fixture${index} = (${JSON.stringify(docs.get(file))}) satisfies T.${type};`, "");
});
lines.push(
  "// Self-test: each of these is wrong on purpose. If the check stopped catching one, tsc reports an unused directive.",
  "// @ts-expect-error unknown enum value",
  'export const wrongEnum = ({ accepted: 1, duplicates: 0, execution_status: "done" }) satisfies T.IngestResponse;',
  "// @ts-expect-error missing key",
  "export const missingKey = ({ accepted: 1, duplicates: 0 }) satisfies T.IngestResponse;",
  "// @ts-expect-error extra key",
  'export const extraKey = ({ accepted: 1, duplicates: 0, execution_status: "running", extra: true }) satisfies T.IngestResponse;',
  "",
);
rmSync(CHECK_DIR, { recursive: true, force: true });
mkdirSync(CHECK_DIR);
writeFileSync(join(CHECK_DIR, "check.ts"), lines.join("\n"));
const tsc = createRequire(import.meta.url).resolve("typescript/bin/tsc");
try {
  execFileSync(
    process.execPath,
    [tsc, "--noEmit", "--strict", "--skipLibCheck", "--target", "es2022", "--module", "esnext", "--moduleResolution", "bundler", "--pretty", "false", join(CHECK_DIR, "check.ts")],
    { cwd: FRONTEND, stdio: "pipe" },
  );
  rmSync(CHECK_DIR, { recursive: true, force: true });
} catch (error) {
  const output = String((error as { stdout?: Buffer }).stdout ?? error);
  // Point each compiler error at the fixture it belongs to.
  const source = lines.join("\n").split("\n");
  for (const line of output.split("\n").filter(Boolean).slice(0, 40)) {
    const match = /check\.ts\((\d+),\d+\): (.*)/.exec(line);
    if (!match) {
      fail(`tsc: ${line}`);
      continue;
    }
    const label = source[Number(match[1]) - 2]?.replace(/^\/\/ /, "") ?? "?";
    fail(`${label}: ${match[2]}`);
  }
  console.error(`(generated file kept for inspection: ${join(CHECK_DIR, "check.ts")})`);
}

// ── 2. Formats ──────────────────────────────────────────────────────────────

const ID = /^(agt|exe|stp|evt|anm|inv|rpl)_[0-9a-f]{32}$/;
const ID_LIKE = /^(agt|exe|stp|evt|anm|inv|rpl)_/;
const TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const TIMESTAMP_LIKE = /^\d{4}-\d{2}-\d{2}T\d{2}:/;
const PREFIX_OF_KEY: Record<string, string> = {
  agent_id: "agt",
  execution_id: "exe",
  original_execution_id: "exe",
  replay_execution_id: "exe",
  replay_of: "exe",
  parent_step_id: "stp",
  step_id: "stp",
  failing_step_id: "stp",
  original_step_id: "stp",
  replay_step_id: "stp",
};

const defined = new Set<string>();
const referenced: [id: string, where: string][] = [];

function walk(node: Node, where: string, visit: (node: Node, key: string | null, where: string) => void, key: string | null = null): void {
  visit(node, key, where);
  if (Array.isArray(node)) node.forEach((item, index) => walk(item, `${where}[${index}]`, visit, key));
  else if (isRecord(node)) for (const [k, value] of Object.entries(node)) walk(value, `${where}.${k}`, visit, k);
}

for (const [file, doc] of docs) {
  walk(doc, file, (node, key, where) => {
    if (typeof node !== "string") return;
    if (ID_LIKE.test(node)) {
      if (!ID.test(node)) return fail(`${where}: "${node}" is not a valid id (prefix_ + 32 lowercase hex)`);
      if (key === "id") defined.add(node);
      else referenced.push([node, where]);
      const prefix = key ? PREFIX_OF_KEY[key] : undefined;
      if (prefix && !node.startsWith(`${prefix}_`)) fail(`${where}: expected a ${prefix}_ id, got "${node}"`);
    }
    if (TIMESTAMP_LIKE.test(node) && !TIMESTAMP.test(node)) {
      fail(`${where}: "${node}" is not a UTC timestamp with milliseconds and a Z suffix`);
    }
  });
}

// ── 3. Consistency ──────────────────────────────────────────────────────────

for (const [id, where] of referenced) {
  if (!defined.has(id)) fail(`${where}: ${id} does not exist in any fixture`);
}

const itemsOf = (file: string): { [k: string]: Node }[] => {
  const doc = docs.get(file);
  return isRecord(doc ?? null) && Array.isArray((doc as { items?: Node }).items) ? ((doc as { items: Node[] }).items.filter(isRecord)) : [];
};
const same = (a: Node, b: Node) => JSON.stringify(a) === JSON.stringify(b);

for (const [file, doc] of docs) {
  if (!isRecord(doc) || !Array.isArray(doc.items)) continue;
  if (doc.total !== doc.items.length) fail(`${file}: total is ${String(doc.total)} but the page holds ${doc.items.length} items`);
}

const executions = itemsOf("executions.list.json");
for (const summary of executions) {
  const id = String(summary.id);
  const trace = docs.get(`executions.trace.${id}.json`);
  const events = docs.get(`executions.events.${id}.json`);
  if (!isRecord(trace ?? null)) {
    fail(`executions.list.json: no executions.trace.${id}.json`);
    continue;
  }
  const execution = (trace as { execution: { [k: string]: Node } }).execution;
  for (const key of Object.keys(summary)) {
    if (!same(summary[key], execution[key])) fail(`executions.trace.${id}.json: execution.${key} differs from executions.list.json`);
  }
  const steps = (trace as { steps: { [k: string]: Node }[] }).steps;
  if (execution.step_count !== steps.length) fail(`executions.trace.${id}.json: step_count ${String(execution.step_count)} but ${steps.length} steps`);
  steps.forEach((step, index) => {
    if (step.ordinal !== index + 1) fail(`executions.trace.${id}.json: steps are not sorted by ordinal`);
    if (step.execution_id !== id) fail(`executions.trace.${id}.json: step ${String(step.id)} belongs to another execution`);
  });
  const anomalies = (trace as { anomalies: Node[] }).anomalies;
  if (execution.anomaly_count !== anomalies.length) fail(`executions.trace.${id}.json: anomaly_count ${String(execution.anomaly_count)} but ${anomalies.length} anomalies`);
  if (!isRecord(events ?? null)) fail(`executions.list.json: no executions.events.${id}.json`);
  else if ((trace as { event_count: Node }).event_count !== (events as { total: Node }).total) fail(`executions.trace.${id}.json: event_count differs from executions.events.${id}.json`);
}

const investigated = new Set(itemsOf("investigations.list.json").map((investigation) => investigation.execution_id));
for (const summary of executions) {
  if (summary.has_investigation !== investigated.has(summary.id)) {
    fail(`executions.list.json: ${String(summary.id)} has_investigation=${String(summary.has_investigation)} disagrees with investigations.list.json`);
  }
}

const all = (prefix: string): Node[] =>
  [...docs].filter(([file]) => file.startsWith(prefix)).flatMap(([, doc]) => (isRecord(doc) && Array.isArray(doc.items) ? doc.items : [doc]));

// Contract §10 (v1.2): what a replay's steps must say about themselves.
const replayModeOf = new Map<string, string>();
for (const replay of [...itemsOf("replays.list.json")]) {
  if (typeof replay.replay_execution_id === "string") replayModeOf.set(replay.replay_execution_id, String(replay.mode));
}
for (const summary of executions) {
  const id = String(summary.id);
  const trace = docs.get(`executions.trace.${id}.json`);
  if (!isRecord(trace ?? null)) continue;
  const steps = (trace as { steps: { [k: string]: Node }[] }).steps;
  const mode = replayModeOf.get(id);
  for (const step of steps) {
    const metadata = isRecord(step.metadata) ? step.metadata : {};
    const source = metadata.replay_source;
    const where = `executions.trace.${id}.json: step ${String(step.ordinal)} ${String(step.name)}`;
    if (summary.replay_of === null) {
      if (source !== undefined) fail(`${where} has metadata.replay_source, but the execution is not a replay`);
      continue;
    }
    if (typeof source !== "string" || !(REPLAY_SOURCES as readonly string[]).includes(source)) {
      fail(`${where}: every step of a replay needs metadata.replay_source (recorded, executed or blocked)`);
      continue;
    }
    if (mode === undefined) fail(`${where}: the execution is a replay, but no replay in replays.list.json points at it`);
    if (mode === "sandbox" && metadata.side_effects === true && source === "executed") {
      fail(`${where}: a tool with side effects ran in a sandbox replay`);
    }
    if (mode === "live" && source !== "executed") fail(`${where}: a live replay serves nothing, so every step is executed`);
    if (source === "blocked" && (step.status !== "failed" || !isRecord(step.error) || step.error.type !== "SandboxRecordingMissing")) {
      fail(`${where}: a blocked step must be failed with error type SandboxRecordingMissing`);
    }
    if (source === "recorded" && (step.tokens_input !== null || step.tokens_output !== null)) {
      fail(`${where}: a step served from a recording used no tokens in the replay`);
    }
  }
}
for (const replay of all("replays.").filter(isRecord)) {
  const comparison = replay.comparison;
  if (!isRecord(comparison) || !Array.isArray(comparison.step_diffs)) continue;
  const trace = docs.get(`executions.trace.${String(replay.replay_execution_id)}.json`);
  const steps = isRecord(trace ?? null) ? (trace as { steps: { [k: string]: Node }[] }).steps : [];
  for (const diff of comparison.step_diffs.filter(isRecord)) {
    const step = steps.find((candidate) => candidate.id === diff.replay_step_id);
    const expected = step && isRecord(step.metadata) ? (step.metadata.replay_source ?? null) : null;
    if (diff.replay_source !== expected) {
      fail(`replay ${String(replay.id)}: step_diffs ordinal ${String(diff.ordinal)} replay_source is ${String(diff.replay_source)}, the replay step says ${String(expected)}`);
    }
  }
}

// ── 4. Coverage ─────────────────────────────────────────────────────────────

/** Every value found at `key` in objects that have all of `shape`'s keys, anywhere under `roots`. */
function valuesAt(roots: Node[], key: string, shape: string[]): Set<Node> {
  const found = new Set<Node>();
  for (const root of roots) {
    walk(root, "", (node) => {
      if (isRecord(node) && shape.every((k) => k in node)) found.add(node[key]);
    });
  }
  return found;
}

const everything = [...docs.values()];
const coverage: [string, readonly string[], Set<Node>][] = [
  ["ExecutionStatus", EXECUTION_STATUSES, valuesAt(all("executions.list."), "status", ["agent_name", "step_count"])],
  ["StepStatus", STEP_STATUSES, valuesAt(all("executions.trace."), "status", ["ordinal", "depth"])],
  ["StepType", STEP_TYPES, valuesAt(all("executions.trace."), "type", ["ordinal", "depth"])],
  ["Severity", SEVERITIES, valuesAt(all("anomalies.list."), "severity", ["rule_id"])],
  ["AnomalyType", ANOMALY_TYPES, valuesAt(all("anomalies.list."), "type", ["rule_id"])],
  ["AnomalyStatus", ANOMALY_STATUSES, valuesAt(all("anomalies.list."), "status", ["rule_id"])],
  ["AgentHealth", AGENT_HEALTHS, valuesAt(all("agents.list."), "health", ["success_rate"])],
  ["InvestigationStatus", INVESTIGATION_STATUSES, valuesAt(all("investigations."), "status", ["trigger", "provider"])],
  ["InvestigationTrigger", INVESTIGATION_TRIGGERS, valuesAt(all("investigations."), "trigger", ["trigger", "provider"])],
  ["InvestigationProvider", INVESTIGATION_PROVIDERS, valuesAt(all("investigations."), "provider", ["trigger", "provider"])],
  ["Confidence", CONFIDENCES, valuesAt(all("investigations."), "confidence", ["supporting_fact_ids"])],
  ["RootCauseStatus", ROOT_CAUSE_STATUSES, valuesAt(all("investigations."), "status", ["signature", "hypothesis_id"])],
  ["EvidenceKind", EVIDENCE_KINDS, valuesAt(everything, "kind", ["label", "ref_id", "observed"])],
  ["ReplayMode", REPLAY_MODES, valuesAt(all("replays."), "mode", ["side_effects_authorized"])],
  ["ReplayStatus", REPLAY_STATUSES, valuesAt(all("replays."), "status", ["side_effects_authorized"])],
  ["ReplayOutcome", REPLAY_OUTCOMES, valuesAt(all("replays."), "outcome", ["step_diffs"])],
  ["StepChange", STEP_CHANGES, valuesAt(all("replays."), "change", ["original_step_id", "replay_step_id"])],
  ["ReplaySource", REPLAY_SOURCES, valuesAt(all("replays."), "replay_source", ["original_step_id", "replay_step_id"])],
  ["EventType", EVENT_TYPES, valuesAt(all("executions.events."), "type", ["seq", "received_at"])],
  ["ErrorCode", ERROR_CODES, valuesAt(all("error."), "code", ["message", "details"])],
];
for (const [name, values, found] of coverage) {
  const missing = values.filter((value) => !found.has(value));
  if (missing.length) fail(`coverage: no fixture exercises ${name} = ${missing.join(", ")}`);
  // null is how the contract says "absent"; it is not a value of the enum.
  const unknown = [...found].filter((value) => value !== null && !values.includes(String(value)));
  if (unknown.length) fail(`coverage: ${name} has values outside the contract: ${unknown.map(String).join(", ")}`);
}

const has = (roots: Node[], test: (node: { [k: string]: Node }) => boolean): boolean => {
  let found = false;
  for (const root of roots) walk(root, "", (node) => void (isRecord(node) && test(node) && (found = true)));
  return found;
};
const traces = all("executions.trace.");
const special: [string, boolean][] = [
  ["a `_truncated` payload marker", has(traces, (n) => n._truncated === true && typeof n.original_bytes === "number" && typeof n.preview === "string")],
  ["a nested step (depth > 0)", has(traces, (n) => "ordinal" in n && typeof n.depth === "number" && n.depth > 0)],
  ["a retried step (attempt > 1)", has(traces, (n) => "ordinal" in n && typeof n.attempt === "number" && n.attempt > 1)],
  ["an execution with cost_usd = null", executions.some((e) => e.cost_usd === null)],
  ["an execution with a cost_usd value", executions.some((e) => typeof e.cost_usd === "number")],
  ["an execution with tokens_total = null", executions.some((e) => e.tokens_total === null)],
  ["a replay execution (replay_of set)", executions.some((e) => e.replay_of !== null)],
  ["an empty list page", [...docs.values()].some((doc) => isRecord(doc) && Array.isArray(doc.items) && doc.items.length === 0)],
  ["a hypothesis with a contradicting fact", has(all("investigations."), (n) => Array.isArray(n.contradicting_fact_ids) && n.contradicting_fact_ids.length > 0)],
  ["a report with evidence gaps", has(all("investigations."), (n) => Array.isArray(n.evidence_gaps) && n.evidence_gaps.length > 0)],
  ["a live replay", has(all("replays."), (n) => n.mode === "live" && n.side_effects_authorized === true)],
  ["a step blocked by the sandbox", has(traces, (n) => "ordinal" in n && isRecord(n.metadata) && n.metadata.replay_source === "blocked")],
  ["a step served from a recording", has(traces, (n) => "ordinal" in n && isRecord(n.metadata) && n.metadata.replay_source === "recorded")],
  ["an agent with no executions", has(all("agents.list."), (n) => "last_execution" in n && n.last_execution === null)],
];
for (const [what, present] of special) if (!present) fail(`coverage: no fixture has ${what}`);

// ── Report ──────────────────────────────────────────────────────────────────

if (problems.length) {
  console.error(`✗ ${problems.length} problem(s) in ${names.length} fixtures:\n`);
  for (const problem of problems) console.error(`  ${problem}`);
  process.exit(1);
}
console.log(`✓ ${names.length} fixtures match lib/api/types.ts`);
console.log(`✓ ${defined.size} ids defined, ${referenced.length} references resolve, timestamps are UTC ms Z`);
console.log(`✓ ${executions.length} executions agree with their trace and events files`);
console.log(`✓ every value of ${coverage.length} enums appears; ${special.length} special cases present`);
