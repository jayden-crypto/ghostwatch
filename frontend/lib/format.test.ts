import { describe, expect, it } from "vitest";

import {
  DASH,
  formatBytes,
  formatCost,
  formatCount,
  formatCountDelta,
  formatDuration,
  formatDurationDelta,
  formatRate,
  formatRelative,
  formatUtc,
  formatUtcTime,
  pluralize,
  shortId,
} from "./format";

describe("formatDuration", () => {
  it.each([
    [0, "0 ms"],
    [842, "842 ms"],
    [999, "999 ms"],
    [1000, "1.0 s"],
    [12_400, "12.4 s"],
    [59_940, "59.9 s"],
    [59_960, "1m 00s"],
    [60_000, "1m 00s"],
    [185_000, "3m 05s"],
    [131_866, "2m 12s"],
    [3_599_600, "1h 00m"],
    [3_720_000, "1h 02m"],
  ])("%d ms → %s", (ms, text) => expect(formatDuration(ms)).toBe(text));

  it("shows unknown as a dash, never as zero", () => {
    expect(formatDuration(null)).toBe(DASH);
    expect(formatDuration(undefined)).toBe(DASH);
  });
});

describe("deltas", () => {
  it("signs differences and keeps unknown unknown", () => {
    expect(formatDurationDelta(1200)).toBe("+1.2 s");
    expect(formatDurationDelta(-340)).toBe("−340 ms");
    expect(formatDurationDelta(0)).toBe("0 ms");
    expect(formatDurationDelta(null)).toBe(DASH);
    expect(formatCountDelta(1500)).toBe("+1,500");
    expect(formatCountDelta(-2)).toBe("−2");
    expect(formatCountDelta(0)).toBe("0");
    expect(formatCountDelta(null)).toBe(DASH);
  });
});

describe("counts, cost and rates", () => {
  it("separates thousands", () => {
    expect(formatCount(45_812)).toBe("45,812");
    expect(formatCount(0)).toBe("0");
    expect(formatCount(null)).toBe(DASH);
  });

  it("formats cost to four decimals and keeps null distinct from zero", () => {
    expect(formatCost(0.0123)).toBe("$0.0123");
    expect(formatCost(0.004225)).toBe("$0.0042");
    expect(formatCost(12.5)).toBe("$12.5000");
    expect(formatCost(0.0000123)).toBe("$0.000012");
    expect(formatCost(0)).toBe("$0.0000");
    expect(formatCost(null)).toBe(DASH);
  });

  it("formats rates as percentages", () => {
    expect(formatRate(1)).toBe("100%");
    expect(formatRate(0.5)).toBe("50%");
    expect(formatRate(0.8888888)).toBe("88.9%");
    expect(formatRate(0)).toBe("0%");
    expect(formatRate(null)).toBe(DASH);
  });

  it("formats payload sizes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(186_368)).toBe("182 KB");
    expect(formatBytes(1_500_000)).toBe("1.4 MB");
    expect(formatBytes(null)).toBe(DASH);
  });

  it("pluralizes", () => {
    expect(pluralize(1, "step")).toBe("1 step");
    expect(pluralize(1200, "step")).toBe("1,200 steps");
    expect(pluralize(2, "anomaly", "anomalies")).toBe("2 anomalies");
  });
});

describe("timestamps", () => {
  const stamp = "2026-11-14T17:20:14.592Z";
  const at = (offsetMs: number) => Date.parse(stamp) + offsetMs;

  it("shows the exact UTC instant", () => {
    expect(formatUtc(stamp)).toBe("2026-11-14 17:20:14.592 UTC");
    expect(formatUtcTime(stamp)).toBe("17:20:14.592");
    expect(formatUtc(null)).toBe(DASH);
    expect(formatUtc("not a date")).toBe("not a date");
  });

  it.each([
    [2_000, "just now"],
    [42_000, "42s ago"],
    [5 * 60_000, "5m ago"],
    [3 * 3_600_000, "3h ago"],
    [2 * 86_400_000, "2d ago"],
    [30 * 86_400_000, "2026-11-14"],
  ])("%d ms later → %s", (offset, text) => expect(formatRelative(stamp, at(offset))).toBe(text));

  it("does not call a timestamp from the future 'ago'", () => {
    expect(formatRelative(stamp, at(-60_000))).toBe("2026-11-14 17:20:14.592 UTC");
    expect(formatRelative(null, at(0))).toBe(DASH);
  });
});

describe("shortId", () => {
  it("shortens contract ids and leaves anything else alone", () => {
    expect(shortId("exe_3f9c2a7e1b4d4e0f9a8b7c6d5e4f3a2b")).toBe("exe_3f9c…3a2b");
    expect(shortId("research-assistant")).toBe("research-assistant");
  });
});
