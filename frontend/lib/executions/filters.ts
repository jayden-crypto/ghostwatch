/**
 * The executions table's filters live in the URL, under the same names the contract uses for
 * `GET /executions` (§4), so a filtered view is a link and the query string maps one to one onto
 * the request.
 *
 * One addition: `range` (1h | 24h | 7d | 30d) is a rolling window. It is resolved to
 * `started_after` when the request is made, so a shared link means "the last 24 hours", not a
 * fixed day.
 */
import {
  EXECUTION_SORT_FIELDS,
  EXECUTION_STATUSES,
  type ExecutionListParams,
  type ExecutionSort,
  type ExecutionStatus,
  type ID,
} from "@/lib/api/types";

export const PAGE_SIZE = 50;
export const DEFAULT_SORT: ExecutionSort = "-started_at";

export const RANGES = { "1h": 3_600_000, "24h": 86_400_000, "7d": 7 * 86_400_000, "30d": 30 * 86_400_000 } as const;
export type Range = keyof typeof RANGES;
export const RANGE_LABEL: Record<Range, string> = { "1h": "Last hour", "24h": "Last 24 hours", "7d": "Last 7 days", "30d": "Last 30 days" };

export interface ExecutionFilters {
  q: string;
  agent_id: ID | null;
  status: ExecutionStatus[];
  range: Range | null;
  started_after: string | null;
  started_before: string | null;
  min_duration_ms: number | null;
  max_duration_ms: number | null;
  has_anomaly: boolean | null;
  is_replay: boolean | null;
  sort: ExecutionSort;
  offset: number;
}

const bool = (value: string | null): boolean | null => (value === "true" ? true : value === "false" ? false : null);

const nonNegativeInt = (value: string | null): number | null => {
  if (value === null || !/^\d+$/.test(value)) return null;
  return Number(value);
};

const timestamp = (value: string | null): string | null => {
  if (!value) return null;
  const time = Date.parse(value);
  return Number.isNaN(time) ? null : new Date(time).toISOString();
};

const isSort = (value: string | null): value is ExecutionSort =>
  value !== null && (EXECUTION_SORT_FIELDS as readonly string[]).includes(value.replace(/^-/, ""));

/** Read the filters from a query string. Anything malformed is ignored rather than sent to the API. */
export function parseFilters(params: URLSearchParams): ExecutionFilters {
  const status = (params.get("status") ?? "")
    .split(",")
    .filter((value): value is ExecutionStatus => (EXECUTION_STATUSES as readonly string[]).includes(value));
  const range = params.get("range");
  const sort = params.get("sort");
  return {
    q: params.get("q") ?? "",
    agent_id: params.get("agent_id") || null,
    status: EXECUTION_STATUSES.filter((value) => status.includes(value)),
    range: range !== null && range in RANGES ? (range as Range) : null,
    started_after: timestamp(params.get("started_after")),
    started_before: timestamp(params.get("started_before")),
    min_duration_ms: nonNegativeInt(params.get("min_duration_ms")),
    max_duration_ms: nonNegativeInt(params.get("max_duration_ms")),
    has_anomaly: bool(params.get("has_anomaly")),
    is_replay: bool(params.get("is_replay")),
    sort: isSort(sort) ? sort : DEFAULT_SORT,
    offset: nonNegativeInt(params.get("offset")) ?? 0,
  };
}

/** The request for these filters. `now` resolves a rolling `range`. */
export function toListParams(filters: ExecutionFilters, now: number): ExecutionListParams {
  const params: ExecutionListParams = { sort: filters.sort, limit: PAGE_SIZE, offset: filters.offset };
  if (filters.q) params.q = filters.q;
  if (filters.agent_id) params.agent_id = filters.agent_id;
  if (filters.status.length) params.status = filters.status;
  if (filters.range) params.started_after = new Date(now - RANGES[filters.range]).toISOString();
  else if (filters.started_after) params.started_after = filters.started_after;
  if (!filters.range && filters.started_before) params.started_before = filters.started_before;
  if (filters.min_duration_ms !== null) params.min_duration_ms = filters.min_duration_ms;
  if (filters.max_duration_ms !== null) params.max_duration_ms = filters.max_duration_ms;
  if (filters.has_anomaly !== null) params.has_anomaly = filters.has_anomaly;
  if (filters.is_replay !== null) params.is_replay = filters.is_replay;
  return params;
}

/** How many filters narrow the list (sorting and paging do not). */
export function activeFilterCount(filters: ExecutionFilters): number {
  return [
    filters.q !== "",
    filters.agent_id !== null,
    filters.status.length > 0,
    filters.range !== null || filters.started_after !== null || filters.started_before !== null,
    filters.min_duration_ms !== null || filters.max_duration_ms !== null,
    filters.has_anomaly !== null,
    filters.is_replay !== null,
  ].filter(Boolean).length;
}

/** Every filter key, set to null: the URL patch that clears them all. */
export const CLEARED = {
  q: null,
  agent_id: null,
  status: null,
  range: null,
  started_after: null,
  started_before: null,
  min_duration_ms: null,
  max_duration_ms: null,
  has_anomaly: null,
  is_replay: null,
  offset: null,
} as const;
