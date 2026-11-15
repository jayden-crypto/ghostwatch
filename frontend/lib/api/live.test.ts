import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./errors";
import { createLiveApi, toQuery } from "./live";

const BASE = "http://localhost:8000/api/v1";

const json = (status: number, body: unknown): Response =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const failure = async (promise: Promise<unknown>): Promise<ApiError> => {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected the request to fail");
};

describe("toQuery", () => {
  it("joins lists with commas and leaves out absent and empty values", () => {
    expect(toQuery({ status: ["failed", "timed_out"], has_anomaly: false, q: "", agent_id: undefined, limit: 50, offset: 0 })).toBe(
      "?status=failed%2Ctimed_out&has_anomaly=false&limit=50&offset=0",
    );
    expect(toQuery({ status: [] })).toBe("");
    expect(toQuery(undefined)).toBe("");
  });
});

describe("live adapter", () => {
  it("calls the contract paths with the contract query string", async () => {
    const fetcher = vi.fn<typeof fetch>(async () => json(200, { items: [], total: 0, limit: 50, offset: 0 }));
    const api = createLiveApi(BASE, fetcher);
    await api.listExecutions({ status: ["failed"], sort: "-duration_ms", limit: 20 });
    await api.getTrace("exe_1");
    await api.statsTimeseries({ window: "24h", bucket: "hour" });
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      `${BASE}/executions?status=failed&sort=-duration_ms&limit=20`,
      `${BASE}/executions/exe_1/trace`,
      `${BASE}/stats/timeseries?window=24h&bucket=hour`,
    ]);
  });

  it("sends JSON bodies for POST and PATCH", async () => {
    const fetcher = vi.fn<typeof fetch>(async () => json(201, {}));
    const api = createLiveApi(BASE, fetcher);
    await api.createReplay("exe_1", { mode: "live", authorize_side_effects: true });
    await api.createInvestigation("exe_1");
    await api.updateAnomaly("anm_1", { status: "resolved" });
    expect(fetcher.mock.calls.map(([url, init]) => [init?.method, url, init?.body])).toEqual([
      ["POST", `${BASE}/executions/exe_1/replay`, '{"mode":"live","authorize_side_effects":true}'],
      ["POST", `${BASE}/investigations/exe_1`, "{}"],
      ["PATCH", `${BASE}/anomalies/anm_1`, '{"status":"resolved"}'],
    ]);
  });

  it("turns the error envelope into an ApiError carrying its code, message and details", async () => {
    const envelope = { error: { code: "validation_error", message: "Request validation failed.", details: [{ loc: ["body", "mode"], msg: "bad" }] } };
    const api = createLiveApi(BASE, async () => json(422, envelope));
    expect(await failure(api.createReplay("exe_1", { mode: "sandbox" }))).toMatchObject({
      code: "validation_error",
      status: 422,
      message: "Request validation failed.",
      details: envelope.error.details,
    });
  });

  it("reports a failure that is not the contract's envelope as invalid_response", async () => {
    const notEnvelope = createLiveApi(BASE, async () => json(500, { detail: "Internal Server Error" }));
    expect(await failure(notEnvelope.health())).toMatchObject({ code: "invalid_response", status: 500 });
    const notJson = createLiveApi(BASE, async () => new Response("<html>502</html>", { status: 502 }));
    expect(await failure(notJson.health())).toMatchObject({ code: "invalid_response", status: 502 });
  });

  it("reports an unreachable backend as network_error and names the address", async () => {
    const api = createLiveApi(BASE, async () => {
      throw new TypeError("Failed to fetch");
    });
    const error = await failure(api.listAgents());
    expect(error).toMatchObject({ code: "network_error", status: null });
    expect(error.message).toContain(BASE);
  });
});
