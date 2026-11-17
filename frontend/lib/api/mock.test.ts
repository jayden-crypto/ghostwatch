import { describe, expect, it } from "vitest";

import { fixtures } from "@/mocks/fixtures";

import { ApiError } from "./errors";
import { createMockApi, type MockState } from "./mock";

/** A mock with no latency, a controllable state and a controllable clock. */
function setup(state: MockState = null) {
  const time = { now: 0 };
  const api = createMockApi({ latency: () => 0, state: () => state, clock: () => time.now });
  return { api, time };
}

const failure = async (promise: Promise<unknown>): Promise<ApiError> => {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected the request to fail");
};

const ids = fixtures["executions.list"].items;
const byKey = (file: "healthy" | "schema_change" | "ghost_invoice" | "running" | "timed_out") =>
  fixtures[`executions.get.${file}`].id;
const rateLimit = fixtures["investigations.create"].execution_id;

describe("executions list", () => {
  it("returns the newest first, 50 per page by default", async () => {
    const page = await setup().api.listExecutions();
    expect(page).toMatchObject({ total: ids.length, limit: 50, offset: 0 });
    expect(page.items.length).toBe(Math.min(50, ids.length));
    const started = page.items.map((e) => e.started_at);
    expect(started).toEqual([...started].sort().reverse());
  });

  it("paginates with limit and offset and clamps limit to 200", async () => {
    const { api } = setup();
    const first = await api.listExecutions({ limit: 10 });
    const second = await api.listExecutions({ limit: 10, offset: 10 });
    expect(first.items).toHaveLength(10);
    expect(second.offset).toBe(10);
    expect(second.items[0].id).not.toBe(first.items[0].id);
    expect(new Set([...first.items, ...second.items].map((e) => e.id)).size).toBe(20);
    expect((await api.listExecutions({ limit: 5000 })).limit).toBe(200);
    expect((await api.listExecutions({ offset: 10_000 })).items).toEqual([]);
  });

  it("filters by status list, agent, anomaly presence and replay", async () => {
    const { api } = setup();
    const failed = await api.listExecutions({ status: ["failed", "timed_out"], limit: 200 });
    expect(failed.items.length).toBeGreaterThan(0);
    expect(failed.items.every((e) => e.status === "failed" || e.status === "timed_out")).toBe(true);

    const agentId = ids[0].agent_id;
    const ofAgent = await api.listExecutions({ agent_id: agentId, limit: 200 });
    expect(ofAgent.total).toBe(ids.filter((e) => e.agent_id === agentId).length);

    const withAnomaly = await api.listExecutions({ has_anomaly: true, limit: 200 });
    expect(withAnomaly.items.every((e) => e.anomaly_count > 0)).toBe(true);
    const without = await api.listExecutions({ has_anomaly: false, limit: 200 });
    expect(withAnomaly.total + without.total).toBe(ids.length);

    const replays = await api.listExecutions({ is_replay: true, limit: 200 });
    expect(replays.items.every((e) => e.replay_of !== null)).toBe(true);
    const ofOriginal = await api.listExecutions({ replay_of: byKey("schema_change") });
    expect(ofOriginal.total).toBe(2);
  });

  it("treats started_after as inclusive and started_before as exclusive", async () => {
    const { api } = setup();
    const pivot = ids[5].started_at;
    const after = await api.listExecutions({ started_after: pivot, limit: 200 });
    const before = await api.listExecutions({ started_before: pivot, limit: 200 });
    expect(after.items.some((e) => e.started_at === pivot)).toBe(true);
    expect(before.items.some((e) => e.started_at === pivot)).toBe(false);
    expect(after.total + before.total).toBe(ids.length);
  });

  it("filters by duration range, leaving out runs with no duration", async () => {
    const page = await setup().api.listExecutions({ min_duration_ms: 2000, max_duration_ms: 10_000, limit: 200 });
    expect(page.items.length).toBeGreaterThan(0);
    expect(page.items.every((e) => e.duration_ms !== null && e.duration_ms >= 2000 && e.duration_ms <= 10_000)).toBe(true);
  });

  it("matches q against an id prefix or part of the agent name", async () => {
    const { api } = setup();
    expect((await api.listExecutions({ q: byKey("healthy").slice(0, 36) })).items.map((e) => e.id)).toContain(byKey("healthy"));
    const named = await api.listExecutions({ q: "invoice", limit: 200 });
    expect(named.items.length).toBeGreaterThan(0);
    expect(named.items.every((e) => e.agent_name === "Invoice Processor")).toBe(true);
  });

  it("sorts by any allowed field with unknown values last in both directions", async () => {
    const { api } = setup();
    for (const sort of ["duration_ms", "-duration_ms", "cost_usd", "-cost_usd"] as const) {
      const field = sort.replace("-", "") as "duration_ms" | "cost_usd";
      const values = (await api.listExecutions({ sort, limit: 200 })).items.map((e) => e[field]);
      const firstNull = values.indexOf(null);
      const known = (firstNull === -1 ? values : values.slice(0, firstNull)) as number[];
      expect(values.slice(known.length).every((value) => value === null)).toBe(true);
      const ordered = [...known].sort((a, b) => (sort.startsWith("-") ? b - a : a - b));
      expect(known).toEqual(ordered);
    }
  });

  it("rejects an unknown sort field with the contract's bad_request envelope", async () => {
    const error = await failure(setup().api.listExecutions({ sort: "agent" as never }));
    expect(error).toMatchObject({ code: "bad_request", status: 400 });
  });
});

describe("single resources", () => {
  it("serves a trace whose execution matches the list row", async () => {
    const { api } = setup();
    const trace = await api.getTrace(byKey("schema_change"));
    expect(trace.execution.status).toBe("failed");
    expect(trace.steps.map((step) => step.name)).toEqual(["plan", "web_search", "parse_results"]);
    expect((await api.getExecution(byKey("schema_change"))).id).toBe(trace.execution.id);
    expect((await api.listEvents(byKey("schema_change"))).total).toBe(trace.event_count);
  });

  it("answers the 404 envelope for unknown ids", async () => {
    const { api } = setup();
    const unknown = "exe_ffffffffffffffffffffffffffffffff";
    for (const request of [api.getTrace(unknown), api.getExecution(unknown), api.listEvents(unknown), api.getAgent("agt_x"), api.getReplay("rpl_x")]) {
      expect(await failure(request)).toMatchObject({ code: "not_found", status: 404 });
    }
  });

  it("returns copies, so a caller cannot change the mock's data", async () => {
    const { api } = setup();
    const first = await api.getTrace(byKey("healthy"));
    first.steps.length = 0;
    expect((await api.getTrace(byKey("healthy"))).steps.length).toBeGreaterThan(0);
  });
});

describe("agents and anomalies", () => {
  it("filters agents by health and q, sorted by name", async () => {
    const { api } = setup();
    const all = await api.listAgents();
    expect(all.items.map((a) => a.name)).toEqual([...all.items.map((a) => a.name)].sort());
    expect((await api.listAgents({ health: ["idle"] })).items.map((a) => a.slug)).toEqual(["pr-reviewer"]);
    expect((await api.listAgents({ q: "TRIAGE" })).items.map((a) => a.slug)).toEqual(["support-triage"]);
  });

  it("filters anomalies by severity list, status list and execution", async () => {
    const { api } = setup();
    const severe = await api.listAnomalies({ severity: ["high", "critical"], status: ["open"] });
    expect(severe.items.length).toBeGreaterThan(0);
    expect(severe.items.every((a) => (a.severity === "high" || a.severity === "critical") && a.status === "open")).toBe(true);
    const ghost = await api.listAnomalies({ execution_id: byKey("ghost_invoice") });
    expect(ghost.items.map((a) => a.type)).toEqual(["ghost_completion"]);
  });

  it("updates an anomaly's status everywhere it appears", async () => {
    const { api } = setup();
    const [ghost] = (await api.listAnomalies({ type: "ghost_completion" })).items;
    const before = (await api.getAgent(ghost.agent_id)).stats.open_anomalies;
    expect((await api.updateAnomaly(ghost.id, { status: "acknowledged" })).status).toBe("acknowledged");
    expect((await api.getAnomaly(ghost.id)).status).toBe("acknowledged");
    expect((await api.getTrace(ghost.execution_id!)).anomalies[0].status).toBe("acknowledged");
    expect((await api.getAgent(ghost.agent_id)).stats.open_anomalies).toBe(before - 1);
  });
});

describe("stats", () => {
  it("computes the same overview and timeseries as the fixtures", async () => {
    const { api } = setup();
    expect(await api.statsOverview("24h")).toEqual(fixtures["stats.overview.24h"]);
    expect(await api.statsOverview("7d")).toEqual(fixtures["stats.overview.7d"]);
    expect(await api.statsOverview("30d")).toEqual(fixtures["stats.overview.30d"]);
    expect(await api.statsTimeseries({ window: "24h" })).toEqual(fixtures["stats.timeseries.24h.hour"]);
    expect(await api.statsTimeseries({ window: "7d" })).toEqual(fixtures["stats.timeseries.7d.day"]);
    expect(await api.statsTimeseries({ window: "30d", bucket: "day" })).toEqual(fixtures["stats.timeseries.30d.day"]);
  });

  it("zero-fills every bucket and narrows to one agent", async () => {
    const { api } = setup();
    const hourly = await api.statsTimeseries({ window: "7d", bucket: "hour" });
    expect(hourly.points).toHaveLength(7 * 24);
    const agentId = ids[0].agent_id;
    const ofAgent = await api.statsTimeseries({ window: "30d", agent_id: agentId });
    const total = ofAgent.points.reduce((sum, p) => sum + p.completed + p.failed + p.timed_out, 0);
    expect(total).toBe(ids.filter((e) => e.agent_id === agentId && e.status !== "running").length);
  });
});

describe("investigations", () => {
  it("answers not_found for an execution that was never investigated", async () => {
    expect(await failure(setup().api.getInvestigation(rateLimit))).toMatchObject({ code: "not_found", status: 404 });
  });

  it("returns the existing completed investigation unless forced", async () => {
    const { api } = setup();
    const existing = await api.getInvestigation(byKey("schema_change"));
    expect(existing.report?.root_cause.status).toBe("confirmed");
    expect(await api.createInvestigation(byKey("schema_change"))).toEqual(existing);
    expect((await api.createInvestigation(byKey("schema_change"), { force: true })).status).toBe("queued");
  });

  it("moves a started investigation from queued to running to completed, then files it", async () => {
    const { api, time } = setup();
    const created = await api.createInvestigation(rateLimit);
    expect(created).toMatchObject({ status: "queued", trigger: "manual", report: null, completed_at: null });
    // The execution shows it has an investigation from the moment one is queued.
    expect((await api.getExecution(rateLimit)).has_investigation).toBe(true);
    expect((await api.createInvestigation(rateLimit)).id).toBe(created.id);

    time.now = 2_000;
    expect((await api.getInvestigation(rateLimit)).status).toBe("running");
    time.now = 5_000;
    const done = await api.getInvestigation(rateLimit);
    expect(done.status).toBe("completed");
    expect(done.report).not.toBeNull();

    expect((await api.getTrace(rateLimit)).execution.has_investigation).toBe(true);
    // It was started now, not at the fixture's timestamp.
    expect(Date.parse(done.completed_at!) - Date.parse(done.created_at)).toBe(4_000);
    expect(Date.now() - Date.parse(done.created_at)).toBeLessThan(60_000);
    expect((await api.listInvestigations({ limit: 200 })).items.map((i) => i.id)).toContain(done.id);
  });

  it("refuses to investigate a running execution or one with no recorded report", async () => {
    const { api } = setup();
    expect(await failure(api.createInvestigation(byKey("running")))).toMatchObject({ code: "conflict", status: 409 });
    expect(await failure(api.createInvestigation(byKey("healthy")))).toMatchObject({ code: "bad_request" });
  });
});

describe("replays", () => {
  it("refuses a live replay without authorization", async () => {
    const error = await failure(setup().api.createReplay(byKey("schema_change"), { mode: "live" }));
    expect(error).toMatchObject({ code: "side_effect_authorization_required", status: 422 });
  });

  it("refuses to replay an execution that is still running", async () => {
    const error = await failure(setup().api.createReplay(byKey("running"), { mode: "sandbox" }));
    expect(error).toMatchObject({ code: "conflict", status: 409 });
  });

  it("creates a pending replay that shows up in the list and on the original", async () => {
    const { api } = setup();
    const replay = await api.createReplay(byKey("schema_change"), { mode: "sandbox", note: "retry" });
    expect(replay).toMatchObject({ status: "pending", mode: "sandbox", side_effects_authorized: false, note: "retry", comparison: null });
    expect(replay.id).toMatch(/^rpl_[0-9a-f]{32}$/);
    expect((await api.listReplays({ original_execution_id: byKey("schema_change") })).total).toBe(3);
    expect((await api.getExecution(byKey("schema_change"))).replay_ids).toContain(replay.id);
    const live = await api.createReplay(byKey("schema_change"), { mode: "live", authorize_side_effects: true });
    expect(live.side_effects_authorized).toBe(true);
  });
});

describe("running executions", () => {
  it("places a running execution at the present, with its events two seconds old", async () => {
    const now = Date.parse("2027-01-01T00:00:00.000Z");
    const api = createMockApi({ latency: () => 0, state: () => null, now: () => now });
    const trace = await api.getTrace(byKey("running"));
    const events = await api.listEvents(byKey("running"));
    expect(Date.parse(events.items.at(-1)!.timestamp)).toBe(now - 2_000);
    expect(Date.parse(trace.execution.started_at)).toBeLessThan(now - 2_000);
    expect(trace.steps.at(-1)).toMatchObject({ status: "running", ended_at: null });
    // Offsets come from the API and must still agree with the moved timestamps.
    for (const step of trace.steps) {
      expect(Date.parse(step.started_at) - Date.parse(trace.execution.started_at)).toBe(step.offset_ms);
    }
    const [first] = (await api.listExecutions({ limit: 1 })).items;
    expect(first.id).toBe(byKey("running"));
  });
});

describe("debug states", () => {
  it("__state=empty empties every list and zeroes the stats", async () => {
    const { api } = setup("empty");
    for (const page of [await api.listAgents(), await api.listExecutions(), await api.listAnomalies(), await api.listInvestigations(), await api.listReplays()]) {
      expect(page).toMatchObject({ items: [], total: 0 });
    }
    expect(await api.statsOverview("7d")).toMatchObject({ total_executions: 0, success_rate: null, avg_duration_ms: null });
    expect((await api.statsTimeseries({ window: "7d" })).points.every((p) => p.completed === 0 && p.avg_duration_ms === null)).toBe(true);
  });

  it("__state=large gives a trace 250 generated steps", async () => {
    const trace = await setup("large").api.getTrace(byKey("healthy"));
    expect(trace.steps).toHaveLength(250);
    expect(trace.execution.step_count).toBe(250);
  });

  it("__state=error fails every request with internal_error", async () => {
    const { api } = setup("error");
    expect(await failure(api.listExecutions())).toMatchObject({ code: "internal_error", status: 500 });
    expect(await failure(api.health())).toMatchObject({ code: "internal_error" });
  });
});
