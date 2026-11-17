/**
 * Display formatting for values that come straight from the contract.
 * A value the API reports as `null` (unknown) is shown as an em dash, never as 0.
 */
export const DASH = "—";

const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** `842 ms`, `12.4 s`, `3m 05s`, `1h 02m`. */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return DASH;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  // 59,960 ms would round to "60.0 s"; hand it to the minutes form instead.
  if (ms < 59_950) return `${(ms / 1000).toFixed(1)} s`;
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 3600) {
    return `${Math.floor(totalSeconds / 60)}m ${String(totalSeconds % 60).padStart(2, "0")}s`;
  }
  const totalMinutes = Math.round(totalSeconds / 60);
  return `${Math.floor(totalMinutes / 60)}h ${String(totalMinutes % 60).padStart(2, "0")}m`;
}

/** A signed duration difference: `+1.2 s`, `−340 ms`, `0 ms`. */
export function formatDurationDelta(ms: number | null | undefined): string {
  if (ms == null) return DASH;
  if (ms === 0) return "0 ms";
  return `${ms > 0 ? "+" : "−"}${formatDuration(Math.abs(ms))}`;
}

/** Whole numbers with thousands separators: `45,812`. */
export function formatCount(value: number | null | undefined): string {
  return value == null ? DASH : integer.format(value);
}

export function formatCountDelta(value: number | null | undefined): string {
  if (value == null) return DASH;
  if (value === 0) return "0";
  return `${value > 0 ? "+" : "−"}${integer.format(Math.abs(value))}`;
}

/** `$0.0123`. Amounts too small for four decimals keep their first two significant digits. */
export function formatCost(usd: number | null | undefined): string {
  if (usd == null) return DASH;
  if (usd === 0) return "$0.0000";
  if (usd < 0.0001) return `$${usd.toPrecision(2)}`;
  return `$${usd.toFixed(4)}`;
}

/** A 0..1 rate as a percentage: `88.9%`, `100%`. */
export function formatRate(rate: number | null | undefined): string {
  if (rate == null) return DASH;
  const percent = rate * 100;
  return `${Number.isInteger(percent) ? percent : percent.toFixed(1)}%`;
}

/** `182 KB`, `1.4 MB`, `512 B` (1 KB = 1024 B). */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return DASH;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** `2026-11-14 17:20:14.592 UTC`: the exact stored instant. */
export function formatUtc(timestamp: string | null | undefined): string {
  if (!timestamp) return DASH;
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  return `${date.toISOString().replace("T", " ").replace("Z", "")} UTC`;
}

/** `17:20:14.592`: time of day in UTC, for rows that share a date. */
export function formatUtcTime(timestamp: string | null | undefined): string {
  if (!timestamp) return DASH;
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? timestamp : date.toISOString().slice(11, 23);
}

/** `just now`, `42s ago`, `5m ago`, `3h ago`, `2d ago`; after a week, the UTC date. */
export function formatRelative(timestamp: string | null | undefined, now: number): string {
  if (!timestamp) return DASH;
  const then = new Date(timestamp).getTime();
  if (Number.isNaN(then)) return timestamp;
  const seconds = Math.round((now - then) / 1000);
  // A timestamp ahead of this clock (skew between machines) is not "ago": show it exactly.
  if (seconds < -5) return formatUtc(timestamp);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 7 * 86_400) return `${Math.floor(seconds / 86_400)}d ago`;
  return new Date(then).toISOString().slice(0, 10);
}

/** `exe_3f9c…3a2b`: the prefix, the first four and the last four characters of an id. */
export function shortId(id: string): string {
  return /^[a-z]{3}_[0-9a-f]{32}$/.test(id) ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
}

export const pluralize = (count: number, noun: string, plural = `${noun}s`): string =>
  `${formatCount(count)} ${count === 1 ? noun : plural}`;
