import { describe, expect, it } from "vitest";

import { activeFilterCount, DEFAULT_SORT, PAGE_SIZE, parseFilters, toListParams } from "./filters";

const parse = (query: string) => parseFilters(new URLSearchParams(query));
const NOW = Date.parse("2026-11-14T18:00:00.000Z");

describe("execution filters", () => {
  it("defaults to everything, newest first", () => {
    const filters = parse("");
    expect(filters).toMatchObject({ q: "", agent_id: null, status: [], range: null, has_anomaly: null, is_replay: null, sort: DEFAULT_SORT, offset: 0 });
    expect(activeFilterCount(filters)).toBe(0);
    expect(toListParams(filters, NOW)).toEqual({ sort: "-started_at", limit: PAGE_SIZE, offset: 0 });
  });

  it("reads every contract filter from the URL", () => {
    const filters = parse(
      "q=invoice&agent_id=agt_1&status=failed,timed_out&started_after=2026-11-13T00:00:00.000Z&started_before=2026-11-14T00:00:00.000Z" +
        "&min_duration_ms=1000&max_duration_ms=60000&has_anomaly=true&is_replay=false&sort=-duration_ms&offset=50",
    );
    expect(toListParams(filters, NOW)).toEqual({
      q: "invoice",
      agent_id: "agt_1",
      status: ["failed", "timed_out"],
      started_after: "2026-11-13T00:00:00.000Z",
      started_before: "2026-11-14T00:00:00.000Z",
      min_duration_ms: 1000,
      max_duration_ms: 60000,
      has_anomaly: true,
      is_replay: false,
      sort: "-duration_ms",
      limit: PAGE_SIZE,
      offset: 50,
    });
    expect(activeFilterCount(filters)).toBe(7);
  });

  it("ignores malformed values instead of sending them", () => {
    const filters = parse("status=failed,exploded&sort=agent&offset=-3&min_duration_ms=abc&has_anomaly=yes&started_after=nonsense&range=5y");
    expect(filters.status).toEqual(["failed"]);
    expect(filters.sort).toBe(DEFAULT_SORT);
    expect(filters.offset).toBe(0);
    expect(filters.min_duration_ms).toBeNull();
    expect(filters.has_anomaly).toBeNull();
    expect(filters.started_after).toBeNull();
    expect(filters.range).toBeNull();
  });

  it("keeps statuses in the contract's order whatever order the URL has", () => {
    expect(parse("status=timed_out,running,failed").status).toEqual(["running", "failed", "timed_out"]);
  });

  it("resolves a rolling range against now, overriding fixed bounds", () => {
    const filters = parse("range=24h&started_after=2020-01-01T00:00:00.000Z&started_before=2020-02-01T00:00:00.000Z");
    const params = toListParams(filters, NOW);
    expect(params.started_after).toBe("2026-11-13T18:00:00.000Z");
    expect(params.started_before).toBeUndefined();
    expect(activeFilterCount(filters)).toBe(1);
  });

  it("accepts ascending sorts on every allowed field", () => {
    for (const sort of ["started_at", "duration_ms", "tokens_total", "cost_usd", "-tokens_total", "-cost_usd"]) {
      expect(parse(`sort=${sort}`).sort).toBe(sort);
    }
  });
});
