"use client";

/** /replays: every replay, newest first, with its outcome at a glance. */
import { History, SearchX, X } from "lucide-react";
import { useState } from "react";

import { OutcomeBadge, ReplayModeBadge, ReplayStatusBadge } from "@/components/data/badges";
import { DataTable, Pagination, type Column } from "@/components/data/data-table";
import { EmptyState } from "@/components/data/empty-state";
import { ErrorState, Refreshing } from "@/components/data/states";
import { IdChip, Timestamp } from "@/components/data/values";
import { Page } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LIST_POLL_MS, useReplays } from "@/lib/api/hooks";
import { REPLAY_STATUSES, type Replay, type ReplayStatus } from "@/lib/api/types";
import { REPLAY_STATUS } from "@/lib/enums";
import { pluralize, shortId } from "@/lib/format";
import { useUrlState } from "@/lib/use-url-state";

const ANY = "any";
const PAGE_SIZE = 50;

const COLUMNS: Column<Replay>[] = [
  { id: "status", header: "Status", cell: (r) => <ReplayStatusBadge status={r.status} />, width: "w-28", skeleton: "w-20" },
  {
    id: "outcome",
    header: "Outcome",
    cell: (r) =>
      r.comparison ? (
        <OutcomeBadge outcome={r.comparison.outcome} />
      ) : r.error ? (
        <code className="font-mono text-xs text-failed" title={r.error.message}>
          {r.error.type}
        </code>
      ) : (
        <span className="text-fg-subtle" title="A comparison exists once the replay run has ended">
          Not compared yet
        </span>
      ),
    width: "w-40",
    skeleton: "w-24",
  },
  { id: "mode", header: "Mode", cell: (r) => <ReplayModeBadge mode={r.mode} />, width: "w-24", skeleton: "w-16" },
  {
    id: "original",
    header: "Original",
    cell: (r) => <IdChip id={r.original_execution_id} href={`/executions/${r.original_execution_id}`} />,
    width: "w-32",
    skeleton: "w-24",
  },
  {
    id: "replay",
    header: "Replay run",
    cell: (r) => (r.replay_execution_id ? <IdChip id={r.replay_execution_id} href={`/executions/${r.replay_execution_id}`} /> : <span className="text-fg-subtle">—</span>),
    width: "w-36",
    skeleton: "w-24",
    showFrom: "xl",
  },
  {
    id: "agent",
    header: "Agent",
    cell: (r) => (r.comparison ? <span className="text-fg-muted">{r.comparison.original.agent_name}</span> : <span className="text-fg-subtle">—</span>),
    width: "w-44",
    skeleton: "w-24",
    showFrom: "wide",
  },
  {
    id: "note",
    header: "Note",
    cell: (r) =>
      r.note ? (
        <span className="block max-w-[9rem] truncate text-fg-muted xl:max-w-[18rem] min-[1400px]:max-w-[26rem]" title={r.note}>
          {r.note}
        </span>
      ) : (
        <span className="text-fg-subtle">—</span>
      ),
    skeleton: "w-48",
  },
  { id: "requested", header: "Requested", cell: (r) => <Timestamp value={r.requested_at} className="text-fg-muted" />, width: "w-24", skeleton: "w-14" },
];

export function ReplaysView() {
  const [params, setParams] = useUrlState();
  const statusParam = params.get("status");
  const status = (REPLAY_STATUSES as readonly string[]).includes(statusParam ?? "") ? (statusParam as ReplayStatus) : null;
  const originalId = params.get("original_execution_id");
  const [offset, setOffset] = useState(0);
  const filtered = status !== null || originalId !== null;

  const { data, error, refetch, isFetching, isPlaceholderData } = useReplays(
    { status: status ?? undefined, original_execution_id: originalId ?? undefined, limit: PAGE_SIZE, offset },
    { refetchInterval: LIST_POLL_MS },
  );
  const change = (patch: Record<string, string | null>) => {
    setOffset(0);
    setParams(patch);
  };
  const clear = () => change({ status: null, original_execution_id: null });

  return (
    <Page
      title="Replays"
      description="Re-runs of recorded executions, each compared with its original. Sandbox unless a live replay was explicitly authorized."
      actions={
        <>
          <Refreshing active={isFetching && data !== undefined} />
          {data && <span className="num text-fg-muted">{pluralize(data.total, "replay")}</span>}
        </>
      }
    >
      <div className="overflow-hidden rounded-lg border border-line-subtle bg-surface">
        <div className="flex flex-wrap items-center gap-2 border-b border-line-subtle px-4 py-3" role="search" aria-label="Filter replays">
          <Select value={status ?? ANY} onValueChange={(next) => change({ status: next === ANY ? null : next })}>
            <SelectTrigger size="sm" aria-label="Status" className="h-7 min-w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>Status: any</SelectItem>
              {REPLAY_STATUSES.map((value) => (
                <SelectItem key={value} value={value}>
                  {REPLAY_STATUS[value].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {originalId && (
            <span className="inline-flex h-7 items-center gap-1.5 rounded-md border border-line pl-2.5 pr-1 text-xs">
              Replays of <code className="font-mono" title={originalId}>{shortId(originalId)}</code>
              <Button variant="ghost" size="icon-xs" aria-label="Show replays of every execution" onClick={() => change({ original_execution_id: null })}>
                <X aria-hidden="true" />
              </Button>
            </span>
          )}
          {filtered && (
            <Button variant="ghost" size="sm" onClick={clear} className="ml-auto text-fg-muted">
              <X aria-hidden="true" />
              Clear filters
            </Button>
          )}
        </div>
        {error ? (
          <ErrorState error={error} onRetry={() => void refetch()} title="Replays could not be loaded" compact />
        ) : (
          <>
            <DataTable
              columns={COLUMNS}
              rows={data?.items}
              rowKey={(replay) => replay.id}
              rowHref={(replay) => `/replays/${replay.id}`}
              rowLabel={(replay) => `Open replay ${replay.id}`}
              caption="Replays"
              stale={isPlaceholderData}
              skeletonRows={8}
              empty={
                <div className="p-6">
                  {filtered ? (
                    <EmptyState
                      icon={SearchX}
                      title="No replays match these filters"
                      description="Loosen or clear the filters to see more."
                      action={
                        <Button variant="outline" size="sm" onClick={clear}>
                          Clear filters
                        </Button>
                      }
                    />
                  ) : (
                    <EmptyState
                      icon={History}
                      title="No replays yet"
                      description="Open any finished execution and choose Replay. A sandbox replay re-runs it against its recorded tool and model outputs and compares the result with the original."
                    />
                  )}
                </div>
              }
            />
            {data && <Pagination total={data.total} limit={data.limit} offset={data.offset} onOffsetChange={setOffset} noun="replays" />}
          </>
        )}
      </div>
    </Page>
  );
}
