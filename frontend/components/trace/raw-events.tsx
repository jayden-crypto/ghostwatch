"use client";

/**
 * The raw event log of an execution (GET /executions/{id}/events), in `seq` order.
 *
 * This is the evidentiary record that steps, status and anomalies are derived from, so it is
 * shown plainly: what was received, when, with its payload exactly as stored.
 */
import { ChevronRight, ScrollText } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { EventTypeLabel } from "@/components/data/badges";
import { Pagination } from "@/components/data/data-table";
import { EmptyState } from "@/components/data/empty-state";
import { JsonViewer } from "@/components/data/json-viewer";
import { ErrorState } from "@/components/data/states";
import { IdChip, Timestamp } from "@/components/data/values";
import { Skeleton } from "@/components/ui/skeleton";
import { useEvents } from "@/lib/api/hooks";
import type { ID, StoredEvent } from "@/lib/api/types";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

/** The contract's maximum page size: most executions fit on one page. */
const PAGE_SIZE = 200;
const GRID = "grid grid-cols-[3rem_11rem_8rem_5.5rem_minmax(0,1fr)] items-center gap-x-3";

function EventRow({
  event,
  open,
  focused,
  onToggle,
  onOpenStep,
}: {
  event: StoredEvent;
  open: boolean;
  focused: boolean;
  onToggle: () => void;
  onOpenStep: (stepId: ID) => void;
}) {
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ block: "center" });
  }, [focused]);
  const stepId = typeof event.payload.step_id === "string" ? event.payload.step_id : null;
  const lag = Date.parse(event.received_at) - Date.parse(event.timestamp);
  return (
    <li ref={ref} data-event-id={event.id} className={cn("border-b border-line-subtle last:border-0", focused && "bg-timed-out/10")}>
      <div className={cn(GRID, "h-[34px] px-4 hover:bg-raised/70")}>
        <button
          type="button"
          aria-expanded={open}
          aria-label={`${open ? "Hide" : "Show"} payload of event ${event.seq}`}
          onClick={onToggle}
          className="num flex items-center gap-1 rounded-sm font-mono text-xs text-fg-muted hover:text-fg"
        >
          <ChevronRight className={cn("size-3 transition-transform duration-150 ease-out", open && "rotate-90")} aria-hidden="true" />
          {event.seq}
        </button>
        <EventTypeLabel type={event.type} />
        <Timestamp value={event.timestamp} mode="time" className="text-fg-muted" />
        <span className="num font-mono text-xs text-fg-subtle" title={`Received ${event.received_at}`}>
          +{formatDuration(Math.max(0, lag))}
        </span>
        <div className="flex min-w-0 items-center gap-3">
          {stepId && (
            <button type="button" onClick={() => onOpenStep(stepId)} className="shrink-0 rounded-sm text-xs text-fg-muted underline-offset-2 hover:text-fg hover:underline">
              Open step
            </button>
          )}
          <code className="truncate font-mono text-xs text-fg-subtle">{JSON.stringify(event.payload)}</code>
        </div>
      </div>
      {open && (
        <div className="flex flex-col gap-2 px-4 pb-3 pl-[4.75rem]">
          <div className="flex items-center gap-4 text-xs text-fg-subtle">
            <IdChip id={event.id} />
            <span>
              recorded <Timestamp value={event.timestamp} mode="utc" />
            </span>
            <span>
              received <Timestamp value={event.received_at} mode="utc" />
            </span>
          </div>
          <JsonViewer value={event.payload} expandDepth={3} label="event payload" />
        </div>
      )}
    </li>
  );
}

export function RawEvents({
  executionId,
  focusedEventId,
  onOpenStep,
}: {
  executionId: ID;
  /** An event to scroll to and open (`?event=evt_…`), for evidence that points at an event. */
  focusedEventId: ID | null;
  onOpenStep: (stepId: ID) => void;
}) {
  const [offset, setOffset] = useState(0);
  const [toggled, setToggled] = useState<ReadonlySet<ID>>(new Set());
  const { data, error, refetch, isPlaceholderData } = useEvents(executionId, { limit: PAGE_SIZE, offset });

  if (error) return <ErrorState error={error} onRetry={() => void refetch()} title="The event log could not be loaded" className="m-6" />;
  if (!data) {
    return (
      <div className="flex flex-col" aria-busy="true" aria-label="Loading events">
        {Array.from({ length: 10 }, (_, index) => (
          <div key={index} className={cn(GRID, "h-[34px] border-b border-line-subtle px-4")}>
            <Skeleton className="h-3 w-6" />
            <Skeleton className="h-3 w-28" />
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-3 w-10" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        ))}
      </div>
    );
  }
  if (data.total === 0) {
    return (
      <EmptyState
        icon={ScrollText}
        title="No events were received for this execution"
        description="Steps and status are derived from events. With none recorded, there is nothing to derive them from."
      />
    );
  }

  const toggle = (id: ID) =>
    setToggled((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  return (
    <div className="flex h-full flex-col">
      <div className={cn(GRID, "h-8 shrink-0 border-b border-line-subtle px-4 text-xs font-medium text-fg-subtle")}>
        <span>Seq</span>
        <span>Type</span>
        <span>Recorded (UTC)</span>
        <span title="Time between the event being recorded by the agent and received by Ghostwatch">Received</span>
        <span>Payload</span>
      </div>
      <ol className={cn("min-h-0 flex-1 overflow-auto transition-opacity duration-150", isPlaceholderData && "opacity-60")}>
        {data.items.map((event) => {
          const focused = event.id === focusedEventId;
          // A focused event starts open; toggling flips whichever state a row started in.
          const open = focused !== toggled.has(event.id);
          return <EventRow key={event.id} event={event} open={open} focused={focused} onToggle={() => toggle(event.id)} onOpenStep={onOpenStep} />;
        })}
      </ol>
      {data.total > data.limit && <Pagination total={data.total} limit={data.limit} offset={data.offset} onOffsetChange={setOffset} noun="events" />}
    </div>
  );
}
