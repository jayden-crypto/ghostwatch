/**
 * Waterfall geometry: where each step's bar sits on the time axis, and where the axis ticks go.
 * Everything is computed from contract fields (`offset_ms`, `duration_ms`, `started_at`,
 * `duration_ms` of the execution). Pure functions.
 */
import type { ExecutionDetail, Step } from "@/lib/api/types";

/**
 * The span of time the axis covers, in ms from the execution's start.
 *
 * A finished execution spans its own duration. A running one spans up to `now`. Either way the
 * span is stretched to include every recorded step, so a bar can never fall off the axis if a
 * step's timing and the execution's disagree.
 */
export function traceSpan(execution: Pick<ExecutionDetail, "started_at" | "duration_ms">, steps: Step[], now: number): number {
  const elapsed = execution.duration_ms ?? Math.max(0, now - Date.parse(execution.started_at));
  const lastStepEnd = steps.reduce((latest, step) => Math.max(latest, step.offset_ms + (step.duration_ms ?? 0)), 0);
  return Math.max(elapsed, lastStepEnd, 1);
}

export interface Bar {
  /** Left edge and width as percentages of the axis. */
  left: number;
  width: number;
  /** The step has not ended: the bar runs to "now" and keeps growing. */
  open: boolean;
  /** The duration drawn, in ms. For an open bar this is the time elapsed so far. */
  durationMs: number;
}

const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));

/** A step's bar. `nowOffset` is "now" in ms from the execution's start, used for steps still running. */
export function barFor(step: Pick<Step, "offset_ms" | "duration_ms">, span: number, nowOffset: number): Bar {
  const open = step.duration_ms === null;
  const start = clamp(step.offset_ms, 0, span);
  const durationMs = open ? Math.max(0, nowOffset - step.offset_ms) : step.duration_ms!;
  const end = clamp(step.offset_ms + durationMs, start, span);
  return { left: (start / span) * 100, width: ((end - start) / span) * 100, open, durationMs };
}

/**
 * Tick positions in ms: round numbers (1, 2 or 5 times a power of ten), at most `maxTicks` of
 * them, always starting at 0.
 */
export function axisTicks(span: number, maxTicks = 6): number[] {
  if (span <= 0) return [0];
  const rough = span / maxTicks;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 5, 10].map((factor) => factor * magnitude).find((candidate) => span / candidate <= maxTicks)!;
  const ticks: number[] = [];
  for (let tick = 0; tick <= span; tick += step) ticks.push(Math.round(tick * 1000) / 1000);
  return ticks;
}

/** Tick labels share one unit so they compare at a glance: `0`, `200 ms`, `400 ms` or `0`, `1.5 s`, `3 s`. */
export function tickLabel(ms: number, span: number): string {
  if (ms === 0) return "0";
  if (span < 1000) return `${ms} ms`;
  if (span < 120_000) return `${Number((ms / 1000).toFixed(2))} s`;
  if (span < 7_200_000) return `${Number((ms / 60_000).toFixed(1))} min`;
  return `${Number((ms / 3_600_000).toFixed(1))} h`;
}
