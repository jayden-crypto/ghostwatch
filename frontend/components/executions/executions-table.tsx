"use client";

/** The executions table, shared by /executions, /traces, the overview and the agent page. */
import { FileSearch, History, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { StatusBadge } from "@/components/data/badges";
import { DataTable, type Column } from "@/components/data/data-table";
import { Cost, Duration, IdChip, Timestamp, Tokens } from "@/components/data/values";
import type { ExecutionSummary } from "@/lib/api/types";
import { formatCount, pluralize } from "@/lib/format";

/** What else is known about a run, as small icons with text alternatives: anomalies, investigation, replay. */
function Flags({ execution }: { execution: ExecutionSummary }) {
  return (
    <span className="flex items-center justify-end gap-2.5 text-fg-muted">
      {execution.anomaly_count > 0 && (
        <span className="inline-flex items-center gap-1 text-timed-out" title={pluralize(execution.anomaly_count, "anomaly", "anomalies")}>
          <TriangleAlert className="size-3.5" aria-hidden="true" />
          <span className="num font-mono text-xs">{execution.anomaly_count}</span>
          <span className="sr-only">{execution.anomaly_count === 1 ? "anomaly" : "anomalies"}</span>
        </span>
      )}
      {execution.has_investigation && (
        <span title="Has an investigation">
          <FileSearch className="size-3.5" aria-hidden="true" />
          <span className="sr-only">Has an investigation</span>
        </span>
      )}
      {execution.replay_of && (
        <span title={`Replay of ${execution.replay_of}`}>
          <History className="size-3.5" aria-hidden="true" />
          <span className="sr-only">Replay</span>
        </span>
      )}
    </span>
  );
}

const COLUMNS: Record<string, Column<ExecutionSummary>> = {
  status: { id: "status", header: "Status", cell: (e) => <StatusBadge status={e.status} />, width: "w-32", skeleton: "w-20" },
  id: { id: "id", header: "Execution", cell: (e) => <IdChip id={e.id} />, width: "w-36", skeleton: "w-24" },
  agent: { id: "agent", header: "Agent", cell: (e) => <span className="text-fg">{e.agent_name}</span>, skeleton: "w-28" },
  error: {
    id: "error",
    header: "Error",
    cell: (e) =>
      e.error ? (
        <span className="block max-w-[22rem] truncate font-mono text-xs text-fg-muted" title={`${e.error.type}: ${e.error.message}`}>
          <span className="text-failed">{e.error.type}</span>: {e.error.message}
        </span>
      ) : null,
    skeleton: "w-0",
    showFrom: "wide",
  },
  started: {
    id: "started",
    header: "Started",
    cell: (e) => <Timestamp value={e.started_at} className="text-fg-muted" />,
    sortKey: "started_at",
    width: "w-28",
    skeleton: "w-14",
  },
  duration: { id: "duration", header: "Duration", cell: (e) => <Duration ms={e.duration_ms} />, align: "right", sortKey: "duration_ms", width: "w-24", skeleton: "w-12" },
  steps: {
    id: "steps",
    header: "Steps",
    cell: (e) => <span className="num font-mono text-xs">{formatCount(e.step_count)}</span>,
    align: "right",
    width: "w-16",
    skeleton: "w-6",
    showFrom: "xl",
  },
  tokens: { id: "tokens", header: "Tokens", cell: (e) => <Tokens value={e.tokens_total} />, align: "right", sortKey: "tokens_total", width: "w-24", skeleton: "w-10" },
  cost: { id: "cost", header: "Cost", cell: (e) => <Cost usd={e.cost_usd} />, align: "right", sortKey: "cost_usd", width: "w-24", skeleton: "w-12", showFrom: "xl" },
  flags: { id: "flags", header: <span className="sr-only">Anomalies, investigation, replay</span>, cell: (e) => <Flags execution={e} />, align: "right", width: "w-24", skeleton: "w-8" },
};

export type ExecutionColumn = keyof typeof COLUMNS;

const FULL: ExecutionColumn[] = ["status", "id", "agent", "error", "started", "duration", "steps", "tokens", "cost", "flags"];
export const COMPACT_COLUMNS: ExecutionColumn[] = ["status", "id", "agent", "started", "duration", "flags"];

export function ExecutionsTable({
  rows,
  columns = FULL,
  sort,
  onSortChange,
  empty,
  stale,
  skeletonRows,
  caption = "Executions",
}: {
  rows: ExecutionSummary[] | undefined;
  columns?: ExecutionColumn[];
  sort?: string;
  onSortChange?: (sort: string) => void;
  empty: ReactNode;
  stale?: boolean;
  skeletonRows?: number;
  caption?: string;
}) {
  return (
    <DataTable
      columns={columns.map((name) => COLUMNS[name])}
      rows={rows}
      rowKey={(execution) => execution.id}
      rowHref={(execution) => `/executions/${execution.id}`}
      rowLabel={(execution) => `Open the trace of ${execution.agent_name} execution ${execution.id}`}
      sort={sort}
      onSortChange={onSortChange}
      empty={empty}
      stale={stale}
      skeletonRows={skeletonRows}
      caption={caption}
    />
  );
}
