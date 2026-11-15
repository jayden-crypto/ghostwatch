/**
 * The mock adapter: an in-memory stand-in for the backend that serves the contract fixtures.
 *
 * It behaves like the API, not like a file server: list endpoints filter, sort and paginate with
 * the contract's query params, unknown ids answer the contract's 404 envelope, and stats are
 * computed from the same executions the lists return. Every call waits 150–400 ms so loading
 * states are visible.
 *
 * Debug override, handled here and nowhere else: `?__state=empty` makes the world empty,
 * `?__state=error` makes every request fail, and `?__state=large` gives every trace 250 generated
 * steps, so each view's empty, error and heavy states can be seen.
 */
import { withSyntheticSteps } from "@/lib/trace/synthetic";
import { fixtures } from "@/mocks/fixtures";

import type { GhostwatchApi } from "./client";
import { ApiError, HTTP_STATUS } from "./errors";
import {
  EXECUTION_SORT_FIELDS,
  type Agent,
  type Anomaly,
  type ErrorCode,
  type ExecutionStatus,
  type ExecutionSummary,
  type ID,
  type Investigation,
  type Json,
  type Page,
  type Replay,
  type StatsBucket,
  type StatsWindow,
  type StoredEvent,
  type Trace,
} from "./types";

export type MockState = "empty" | "error" | "large" | null;

export interface MockOptions {
  /** Milliseconds each call waits. */
  latency?: () => number;
  state?: () => MockState;
  /** Monotonic milliseconds; drives how an investigation started here moves from queued to completed. */
  clock?: () => number;
  /** Wall-clock milliseconds, used to place executions that are still running. */
  now?: () => number;
}

const HOUR = 3_600_000;
const DAY = 24 * HOUR;
const BUCKET_MS: Record<StatsBucket, number> = { hour: HOUR, day: DAY };
const WINDOW_MS: Record<StatsWindow, number> = { "24h": DAY, "7d": 7 * DAY, "30d": 30 * DAY };

/** How long a mock investigation stays queued, and when it completes, after POST. */
const QUEUED_MS = 1_500;
const COMPLETED_MS = 4_000;

function stateFromUrl(): MockState {
  if (typeof window === "undefined") return null;
  const value = new URLSearchParams(window.location.search).get("__state");
  return value === "empty" || value === "error" || value === "large" ? value : null;
}

const fail = (code: ErrorCode, message: string, details: Json = null): never => {
  throw new ApiError(code, message, HTTP_STATUS[code], details);
};

function paginate<T>(items: T[], params: { limit?: number; offset?: number } = {}): Page<T> {
  const limit = Math.min(200, Math.max(1, Math.trunc(params.limit ?? 50)));
  const offset = Math.max(0, Math.trunc(params.offset ?? 0));
  return { items: items.slice(offset, offset + limit), total: items.length, limit, offset };
}

const contains = (text: string, part: string) => text.toLowerCase().includes(part.toLowerCase());

/** Ascending or descending by `key`; unknown (null) values sort last in both directions. */
function sortBy<T>(items: T[], key: (item: T) => number | string | null, descending: boolean): T[] {
  return [...items].sort((a, b) => {
    const [x, y] = [key(a), key(b)];
    if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;
    const order = x < y ? -1 : x > y ? 1 : 0;
    return descending ? -order : order;
  });
}

export function createMockApi(options: MockOptions = {}): GhostwatchApi {
  const latency = options.latency ?? (() => 150 + Math.random() * 250);
  const state = options.state ?? stateFromUrl;
  const clock = options.clock ?? (() => performance.now());
  const now = options.now ?? (() => Date.now());

  // The fixtures are the database. Rows that requests can change are copied first.
  const named = <T>(prefix: string): Map<ID, T> =>
    new Map(
      Object.entries(fixtures)
        .filter(([name]) => name.startsWith(prefix))
        .map(([name, value]) => [name.slice(prefix.length), structuredClone(value) as T]),
    );
  const db = {
    agents: structuredClone(fixtures["agents.list"].items),
    executions: structuredClone(fixtures["executions.list"].items),
    traces: named<Trace>("executions.trace."),
    events: named<Page<StoredEvent>>("executions.events."),
    anomalies: structuredClone(fixtures["anomalies.list"].items),
    investigations: structuredClone(fixtures["investigations.list"].items),
    replays: structuredClone(fixtures["replays.list"].items),
  };
  // The fixtures are a snapshot, but an execution that is still running is "now" by definition.
  // Its timestamps are moved so its latest event happened two seconds ago; nothing else changes.
  for (const execution of db.executions.filter((e) => e.status === "running")) {
    const trace = db.traces.get(execution.id);
    const events = db.events.get(execution.id)?.items ?? [];
    const latest = Math.max(Date.parse(execution.started_at), ...events.map((event) => Date.parse(event.timestamp)));
    const shift = now() - 2_000 - latest;
    const move = (timestamp: string) => new Date(Date.parse(timestamp) + shift).toISOString();
    execution.started_at = move(execution.started_at);
    if (trace) {
      trace.execution.started_at = execution.started_at;
      for (const step of trace.steps) {
        step.started_at = move(step.started_at);
        if (step.ended_at) step.ended_at = move(step.ended_at);
      }
    }
    for (const event of events) {
      event.timestamp = move(event.timestamp);
      event.received_at = move(event.received_at);
    }
    for (const agent of db.agents) {
      if (agent.stats.last_execution?.id === execution.id) agent.stats.last_execution.started_at = execution.started_at;
    }
  }

  /** Investigations started here that have not completed yet, by execution id. */
  const inFlight = new Map<ID, { startedAt: number; result: Investigation }>();

  // The fixture world is a snapshot; its "now" is the last bucket of the 24 h timeseries fixture.
  const currentHour = Date.parse(fixtures["stats.timeseries.24h.hour"].points.at(-1)!.bucket_start);

  const empty = () => state() === "empty";
  const rows = <K extends "agents" | "executions" | "anomalies" | "investigations" | "replays">(table: K): (typeof db)[K] =>
    (empty() ? [] : db[table]) as (typeof db)[K];

  async function respond<T>(produce: () => T): Promise<T> {
    await new Promise((resolve) => setTimeout(resolve, latency()));
    if (state() === "error") fail("internal_error", fixtures["error.internal_error"].error.message);
    // A copy, as a real response would be: callers can never reach into the mock's state.
    return structuredClone(produce());
  }

  const executionOrFail = (executionId: ID): ExecutionSummary =>
    rows("executions").find((execution) => execution.id === executionId) ??
    fail("not_found", `Execution ${executionId} does not exist.`);

  const traceOrFail = (executionId: ID): Trace => {
    executionOrFail(executionId);
    return db.traces.get(executionId) ?? fail("not_found", `Execution ${executionId} does not exist.`);
  };

  const windowStart = (window: StatsWindow, bucket: StatsBucket): number => {
    const size = BUCKET_MS[bucket];
    return Math.floor(currentHour / size) * size + size - WINDOW_MS[window];
  };
  const defaultBucket = (window: StatsWindow): StatsBucket => (window === "24h" ? "hour" : "day");
  const count = (list: ExecutionSummary[], status: ExecutionStatus) => list.filter((e) => e.status === status).length;
  const averageDuration = (list: ExecutionSummary[]): number | null =>
    list.length ? Math.round(list.reduce((sum, e) => sum + (e.duration_ms ?? 0), 0) / list.length) : null;

  const latestInvestigation = (executionId: ID): Investigation | undefined =>
    sortBy(
      rows("investigations").filter((investigation) => investigation.execution_id === executionId),
      (investigation) => investigation.created_at,
      true,
    )[0];

  /** Where an investigation started here stands now; files it once it has completed. */
  function progress(executionId: ID): Investigation | undefined {
    const run = inFlight.get(executionId);
    if (!run) return undefined;
    const elapsed = clock() - run.startedAt;
    if (elapsed < COMPLETED_MS) {
      return { ...run.result, status: elapsed < QUEUED_MS ? "queued" : "running", completed_at: null, error: null, report: null };
    }
    inFlight.delete(executionId);
    db.investigations = [run.result, ...db.investigations.filter((investigation) => investigation.id !== run.result.id)];
    return run.result;
  }

  return {
    health: () => respond(() => fixtures["health.get"]),

    listAgents: (params = {}) =>
      respond(() => {
        let list: Agent[] = rows("agents");
        if (params.q) list = list.filter((agent) => contains(agent.name, params.q!) || contains(agent.slug, params.q!));
        if (params.health?.length) list = list.filter((agent) => params.health!.includes(agent.stats.health));
        const sort = params.sort ?? "name";
        const field = sort.replace(/^-/, "");
        if (field !== "name" && field !== "created_at") fail("bad_request", `Unknown sort field '${field}'. Allowed: name, created_at.`);
        return paginate(sortBy(list, (agent) => (field === "name" ? agent.name.toLowerCase() : agent.created_at), sort.startsWith("-")), params);
      }),

    getAgent: (agentId) =>
      respond(() => rows("agents").find((agent) => agent.id === agentId) ?? fail("not_found", `Agent ${agentId} does not exist.`)),

    listExecutions: (params = {}) =>
      respond(() => {
        let list: ExecutionSummary[] = rows("executions");
        if (params.agent_id) list = list.filter((e) => e.agent_id === params.agent_id);
        if (params.status?.length) list = list.filter((e) => params.status!.includes(e.status));
        // started_after is inclusive and started_before exclusive, as the backend implements them.
        if (params.started_after) list = list.filter((e) => e.started_at >= params.started_after!);
        if (params.started_before) list = list.filter((e) => e.started_at < params.started_before!);
        if (params.min_duration_ms !== undefined) list = list.filter((e) => e.duration_ms !== null && e.duration_ms >= params.min_duration_ms!);
        if (params.max_duration_ms !== undefined) list = list.filter((e) => e.duration_ms !== null && e.duration_ms <= params.max_duration_ms!);
        if (params.has_anomaly !== undefined) list = list.filter((e) => e.anomaly_count > 0 === params.has_anomaly);
        if (params.is_replay !== undefined) list = list.filter((e) => (e.replay_of !== null) === params.is_replay);
        if (params.replay_of) list = list.filter((e) => e.replay_of === params.replay_of);
        if (params.q) list = list.filter((e) => e.id.startsWith(params.q!) || contains(e.agent_name, params.q!));
        const sort = params.sort ?? "-started_at";
        const field = sort.replace(/^-/, "") as (typeof EXECUTION_SORT_FIELDS)[number];
        if (!EXECUTION_SORT_FIELDS.includes(field)) {
          fail("bad_request", `Unknown sort field '${field}'. Allowed: ${EXECUTION_SORT_FIELDS.join(", ")}.`);
        }
        return paginate(sortBy(list, (e) => e[field], sort.startsWith("-")), params);
      }),

    getExecution: (executionId) => respond(() => traceOrFail(executionId).execution),

    getTrace: (executionId) =>
      respond(() => (state() === "large" ? withSyntheticSteps(traceOrFail(executionId), 250) : traceOrFail(executionId))),

    listEvents: (executionId, params) =>
      respond(() => {
        executionOrFail(executionId);
        return paginate(db.events.get(executionId)?.items ?? [], params);
      }),

    statsOverview: (window = "7d") =>
      respond(() => {
        const start = new Date(windowStart(window, defaultBucket(window))).toISOString();
        const list = rows("executions").filter((e) => e.started_at >= start);
        const terminal = list.filter((e) => e.status !== "running");
        return {
          window,
          total_agents: rows("agents").length,
          total_executions: list.length,
          completed: count(list, "completed"),
          failed: count(list, "failed"),
          timed_out: count(list, "timed_out"),
          running: count(list, "running"),
          success_rate: terminal.length ? count(list, "completed") / terminal.length : null,
          avg_duration_ms: averageDuration(terminal),
          open_anomalies: rows("anomalies").filter((anomaly) => anomaly.status === "open").length,
        };
      }),

    statsTimeseries: (params = {}) =>
      respond(() => {
        const window = params.window ?? "7d";
        const bucket = params.bucket ?? defaultBucket(window);
        const size = BUCKET_MS[bucket];
        const start = windowStart(window, bucket);
        // Running executions are in the overview but not in the points, as on the backend.
        const terminal = rows("executions").filter(
          (e) => e.status !== "running" && (!params.agent_id || e.agent_id === params.agent_id),
        );
        const points = Array.from({ length: WINDOW_MS[window] / size }, (_, index) => {
          const from = new Date(start + index * size).toISOString();
          const to = new Date(start + (index + 1) * size).toISOString();
          const inBucket = terminal.filter((e) => e.started_at >= from && e.started_at < to);
          return {
            bucket_start: from,
            completed: count(inBucket, "completed"),
            failed: count(inBucket, "failed"),
            timed_out: count(inBucket, "timed_out"),
            avg_duration_ms: averageDuration(inBucket),
          };
        });
        return { window, bucket, points };
      }),

    listAnomalies: (params = {}) =>
      respond(() => {
        let list: Anomaly[] = rows("anomalies");
        if (params.agent_id) list = list.filter((a) => a.agent_id === params.agent_id);
        if (params.execution_id) list = list.filter((a) => a.execution_id === params.execution_id);
        if (params.type) list = list.filter((a) => a.type === params.type);
        if (params.severity?.length) list = list.filter((a) => params.severity!.includes(a.severity));
        if (params.status?.length) list = list.filter((a) => params.status!.includes(a.status));
        return paginate(sortBy(list, (a) => a.detected_at, true), params);
      }),

    getAnomaly: (anomalyId) =>
      respond(() => rows("anomalies").find((a) => a.id === anomalyId) ?? fail("not_found", `Anomaly ${anomalyId} does not exist.`)),

    updateAnomaly: (anomalyId, body) =>
      respond(() => {
        const anomaly = rows("anomalies").find((a) => a.id === anomalyId) ?? fail("not_found", `Anomaly ${anomalyId} does not exist.`);
        const agent = db.agents.find((a) => a.id === anomaly.agent_id);
        if (agent) agent.stats.open_anomalies += Number(body.status === "open") - Number(anomaly.status === "open");
        anomaly.status = body.status;
        const onTrace = anomaly.execution_id && db.traces.get(anomaly.execution_id)?.anomalies.find((a) => a.id === anomalyId);
        if (onTrace) onTrace.status = body.status;
        return anomaly;
      }),

    listInvestigations: (params = {}) =>
      respond(() => {
        let list: Investigation[] = rows("investigations");
        if (params.status) list = list.filter((i) => i.status === params.status);
        if (params.agent_id) {
          const ofAgent = new Set(rows("executions").filter((e) => e.agent_id === params.agent_id).map((e) => e.id));
          list = list.filter((i) => ofAgent.has(i.execution_id));
        }
        return paginate(sortBy(list, (i) => i.created_at, true), params);
      }),

    getInvestigation: (executionId) =>
      respond(
        () =>
          progress(executionId) ??
          latestInvestigation(executionId) ??
          fail("not_found", `No investigation exists for execution ${executionId}.`),
      ),

    createInvestigation: (executionId, body = {}) =>
      respond(() => {
        const execution = executionOrFail(executionId);
        if (execution.status === "running") fail("conflict", fixtures["error.conflict"].error.message);
        const running = progress(executionId);
        if (running && running.status !== "completed" && running.status !== "failed") return running;
        const existing = latestInvestigation(executionId);
        if (existing?.status === "completed" && !body.force) return existing;
        // The mock cannot investigate: it can only replay a report the fixtures already hold.
        const manual = fixtures["investigations.get.manual_result"];
        const result =
          existing ??
          (manual.execution_id === executionId
            ? manual
            : fail("bad_request", `Mock mode has no investigation report for execution ${executionId}, so it cannot start one.`));
        // It starts now and, in this mock, takes COMPLETED_MS; the report itself is the recorded one.
        const created = now();
        inFlight.set(executionId, {
          startedAt: clock(),
          result: {
            ...result,
            trigger: "manual",
            created_at: new Date(created).toISOString(),
            completed_at: new Date(created + COMPLETED_MS).toISOString(),
          },
        });
        for (const row of [db.executions.find((e) => e.id === executionId), db.traces.get(executionId)?.execution]) {
          if (row) row.has_investigation = true;
        }
        return progress(executionId)!;
      }),

    listReplays: (params = {}) =>
      respond(() => {
        let list: Replay[] = rows("replays");
        if (params.original_execution_id) list = list.filter((r) => r.original_execution_id === params.original_execution_id);
        if (params.status) list = list.filter((r) => r.status === params.status);
        return paginate(sortBy(list, (r) => r.requested_at, true), params);
      }),

    getReplay: (replayId) =>
      respond(() => rows("replays").find((r) => r.id === replayId) ?? fail("not_found", `Replay ${replayId} does not exist.`)),

    createReplay: (executionId, body) =>
      respond(() => {
        executionOrFail(executionId);
        if (body.mode === "live" && body.authorize_side_effects !== true) {
          fail("side_effect_authorization_required", fixtures["error.side_effect_authorization_required"].error.message);
        }
        // No replay worker exists in mock mode, so a replay created here stays pending.
        const replay: Replay = {
          ...fixtures["replays.create"],
          id: `rpl_${Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("")}`,
          original_execution_id: executionId,
          mode: body.mode,
          side_effects_authorized: body.mode === "live",
          note: body.note ?? null,
          requested_at: new Date().toISOString(),
        };
        db.replays = [replay, ...db.replays];
        const original = db.traces.get(executionId)?.execution;
        if (original) original.replay_ids = [...original.replay_ids, replay.id];
        return replay;
      }),
  };
}

export const mockApi = createMockApi();
