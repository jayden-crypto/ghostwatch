import { describe, expect, it } from "vitest";

import type { Step } from "@/lib/api/types";
import { fixtures } from "@/mocks/fixtures";

import { axisTicks, barFor, tickLabel, traceSpan } from "./layout";
import { withSyntheticSteps } from "./synthetic";
import { ancestorsOf, buildTree, reveal, visibleRows } from "./tree";

const digest = fixtures["executions.trace.exe_00000000000000000000000000000061"];
const rateLimit = fixtures["executions.trace.exe_00000000000000000000000000000048"];

/** A minimal step; only the fields the tree and layout read matter. */
const step = (ordinal: number, parent: number | null, extra: Partial<Step> = {}): Step => ({
  ...digest.steps[0],
  id: `s${ordinal}`,
  ordinal,
  parent_step_id: parent === null ? null : `s${parent}`,
  name: `step_${ordinal}`,
  ...extra,
});

describe("buildTree", () => {
  it("nests steps under their parent and counts descendants", () => {
    const tree = buildTree(digest.steps);
    expect(tree.roots.map((node) => node.step.name)).toEqual(["load_schedule", "fetch_tickets", "summarize", "send_digest", "report"]);
    const summarize = tree.roots[2];
    expect(summarize.children.map((node) => node.step.name)).toEqual(["summarize_batch", "summarize_batch"]);
    expect(summarize.descendantCount).toBe(2);
    expect(summarize.children.every((node) => node.depth === 1)).toBe(true);
  });

  it("derives the same depth the API reports", () => {
    const tree = buildTree(digest.steps);
    for (const node of tree.byId.values()) expect(node.depth).toBe(node.step.depth);
  });

  it("counts the attempts of a retried step", () => {
    const tree = buildTree(rateLimit.steps);
    const attempts = tree.roots.filter((node) => node.step.name === "retrieve_kb");
    expect(attempts.map((node) => node.step.attempt)).toEqual([1, 2, 3]);
    expect(attempts.every((node) => node.attempts === 3)).toBe(true);
    expect(tree.roots[0].attempts).toBe(1);
  });

  it("orders by ordinal whatever order the steps arrive in", () => {
    const tree = buildTree([step(3, 1), step(1, null), step(2, 1)]);
    expect(tree.roots[0].children.map((node) => node.step.ordinal)).toEqual([2, 3]);
  });

  it("makes a step with an unknown parent a root", () => {
    const tree = buildTree([step(1, null), step(2, 99)]);
    expect(tree.roots.map((node) => node.step.ordinal)).toEqual([1, 2]);
    expect(tree.parentOf.has("s2")).toBe(false);
  });

  it("survives a parent chain that loops", () => {
    const tree = buildTree([step(1, 2), step(2, 1), step(3, 2)]);
    expect(visibleRows(tree, new Set())).toHaveLength(3);
  });
});

describe("visibleRows", () => {
  const tree = buildTree([step(1, null), step(2, 1), step(3, 2), step(4, 1), step(5, null)]);

  it("lists every step depth first", () => {
    const rows = visibleRows(tree, new Set());
    expect(rows.map((row) => [row.step.ordinal, row.depth])).toEqual([[1, 0], [2, 1], [3, 2], [4, 1], [5, 0]]);
    expect(rows.map((row) => row.hasChildren)).toEqual([true, true, false, false, false]);
  });

  it("hides everything under a collapsed step", () => {
    expect(visibleRows(tree, new Set(["s2"])).map((row) => row.step.ordinal)).toEqual([1, 2, 4, 5]);
    expect(visibleRows(tree, new Set(["s1"])).map((row) => row.step.ordinal)).toEqual([1, 5]);
    expect(visibleRows(tree, new Set(["s1"]))[0].collapsed).toBe(true);
  });

  it("reveals a hidden step by opening its ancestors only", () => {
    expect(ancestorsOf(tree, "s3")).toEqual(["s2", "s1"]);
    const collapsed = new Set(["s1", "s2", "s5"]);
    const opened = reveal(tree, collapsed, "s3");
    expect([...opened]).toEqual(["s5"]);
    expect(reveal(tree, opened, "s3")).toBe(opened);
  });
});

describe("waterfall layout", () => {
  it("spans the execution's duration when it has finished", () => {
    expect(traceSpan(digest.execution, digest.steps, 0)).toBe(digest.execution.duration_ms);
  });

  it("spans up to now while the execution is running", () => {
    const running = { started_at: "2026-11-14T18:00:00.000Z", duration_ms: null };
    const now = Date.parse(running.started_at) + 5_000;
    expect(traceSpan(running, [], now)).toBe(5_000);
  });

  it("never lets a recorded step fall off the axis", () => {
    const late = step(1, null, { offset_ms: 900, duration_ms: 400 });
    expect(traceSpan({ started_at: "2026-11-14T18:00:00.000Z", duration_ms: 1000 }, [late], 0)).toBe(1300);
  });

  it("positions a bar by offset and sizes it by duration", () => {
    expect(barFor({ offset_ms: 250, duration_ms: 500 }, 1000, 0)).toEqual({ left: 25, width: 50, open: false, durationMs: 500 });
    expect(barFor({ offset_ms: 0, duration_ms: 0 }, 1000, 0)).toMatchObject({ left: 0, width: 0 });
  });

  it("runs an unfinished step's bar to now", () => {
    expect(barFor({ offset_ms: 400, duration_ms: null }, 2000, 1400)).toEqual({ left: 20, width: 50, open: true, durationMs: 1000 });
  });

  it("clamps a bar to the axis", () => {
    const bar = barFor({ offset_ms: 800, duration_ms: 900 }, 1000, 0);
    expect(bar.left + bar.width).toBeLessThanOrEqual(100);
    expect(barFor({ offset_ms: 5000, duration_ms: null }, 1000, 900)).toMatchObject({ left: 100, width: 0 });
  });

  it.each([
    [361, [0, 100, 200, 300]],
    [1000, [0, 200, 400, 600, 800, 1000]],
    [4271, [0, 1000, 2000, 3000, 4000]],
    [131_866, [0, 50_000, 100_000]],
  ])("puts round ticks on a %d ms axis", (span, ticks) => {
    expect(axisTicks(span)).toEqual(ticks);
  });

  it("labels ticks in one unit per axis", () => {
    expect(tickLabel(0, 361)).toBe("0");
    expect(tickLabel(200, 361)).toBe("200 ms");
    expect(tickLabel(1500, 4271)).toBe("1.5 s");
    expect(tickLabel(100_000, 131_866)).toBe("1.7 min");
  });
});

describe("large trace", () => {
  it("builds and flattens 250 steps", () => {
    const large = withSyntheticSteps(digest, 250);
    expect(large.steps).toHaveLength(250);
    const tree = buildTree(large.steps);
    const rows = visibleRows(tree, new Set());
    expect(rows).toHaveLength(250);
    expect(Math.max(...rows.map((row) => row.depth))).toBe(2);
    expect(rows.map((row) => row.step.ordinal)).toEqual(large.steps.map((s) => s.ordinal));
    const span = traceSpan(large.execution, large.steps, 0);
    for (const row of rows) {
      const bar = barFor(row.step, span, 0);
      expect(bar.left).toBeGreaterThanOrEqual(0);
      expect(bar.left + bar.width).toBeLessThanOrEqual(100.0001);
    }
  });
});
