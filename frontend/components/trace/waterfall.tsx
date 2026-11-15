"use client";

/**
 * The trace waterfall: one row per step, a tree on the left and a time axis on the right.
 *
 * A bar's position and width come from the step's `offset_ms` and `duration_ms` relative to the
 * span of the execution. Rows are virtualised, so a trace with hundreds of steps scrolls as
 * smoothly as one with five.
 */
import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronRight } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ID } from "@/lib/api/types";
import { metaOf, STEP_STATUS, STEP_TYPE, TONE_TEXT } from "@/lib/enums";
import { formatDuration } from "@/lib/format";
import { axisTicks, barFor, tickLabel } from "@/lib/trace/layout";
import type { TraceRow } from "@/lib/trace/tree";
import { cn } from "@/lib/utils";

export const ROW_HEIGHT = 28;
const INDENT = 14;
/** The tree column: wide enough for a nested name, never more than its share of a narrow pane. */
const COLUMNS = "grid grid-cols-[minmax(180px,36%)_minmax(0,1fr)]";

const BAR_TONE = {
  completed: "bg-fg-muted/55 group-hover/row:bg-fg-muted/80",
  failed: "bg-failed",
  running: "bar-live bg-running/70",
} as const;

interface WaterfallProps {
  rows: TraceRow[];
  /** The time the axis covers, in ms from the execution's start. */
  span: number;
  /** "Now" in ms from the execution's start; bars of running steps end here. */
  nowOffset: number;
  selectedId: ID | null;
  /** The keyboard cursor: the row j/k last moved to. */
  cursorId: ID | null;
  /** Steps referenced by the active anomaly's evidence. */
  highlighted: ReadonlySet<ID>;
  onSelect: (stepId: ID) => void;
  onToggle: (stepId: ID) => void;
  /** Changes when a deep link should be scrolled to and flashed. */
  focusRequest: { stepId: ID; at: number } | null;
}

export function Waterfall({ rows, span, nowOffset, selectedId, cursorId, highlighted, onSelect, onToggle, focusRequest }: WaterfallProps) {
  const scroller = useRef<HTMLDivElement>(null);
  // TanStack Virtual returns functions the React Compiler cannot memoize, so it leaves this component
  // uncompiled. That is the intended behaviour: the virtualizer does its own bookkeeping.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });
  const ticks = useMemo(() => axisTicks(span), [span]);
  const indexOf = useMemo(() => new Map(rows.map((row, index) => [row.step.id, index])), [rows]);

  // Keep the keyboard cursor on screen as it moves.
  useEffect(() => {
    const index = cursorId === null ? undefined : indexOf.get(cursorId);
    if (index !== undefined) virtualizer.scrollToIndex(index, { align: "auto" });
  }, [cursorId, indexOf, virtualizer]);

  // A deep link (?step=…) brings its step to the middle of the view.
  useEffect(() => {
    const index = focusRequest ? indexOf.get(focusRequest.stepId) : undefined;
    if (index !== undefined) virtualizer.scrollToIndex(index, { align: "center" });
    // Only a new request should scroll; row changes while polling must not yank the view back.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusRequest]);

  return (
    <div ref={scroller} className="h-full overflow-auto" data-testid="waterfall">
      <div className="min-w-[380px]">
        {/* Axis header */}
        <div className={cn(COLUMNS, "sticky top-0 z-20 h-8 border-b border-line-subtle bg-background text-xs text-fg-subtle")}>
          <div className="flex items-center border-r border-line-subtle pl-4">
            <span>Step</span>
          </div>
          <div className="relative mx-3" aria-hidden="true">
            {ticks.map((tick) => (
              <span
                key={tick}
                className="num absolute top-1/2 -translate-y-1/2 whitespace-nowrap font-mono text-[11px]"
                style={tick === 0 ? { left: 0 } : { left: `${(tick / span) * 100}%`, transform: "translate(-50%, -50%)" }}
              >
                {tickLabel(tick, span)}
              </span>
            ))}
          </div>
        </div>

        <div role="tree" aria-label="Execution steps" className="relative" style={{ height: virtualizer.getTotalSize() }}>
          {/* Gridlines behind the bars, one per axis tick */}
          <div className={cn(COLUMNS, "pointer-events-none absolute inset-0")} aria-hidden="true">
            <div className="border-r border-line-subtle" />
            <div className="relative mx-3">
              {ticks.map((tick) => (
                <span key={tick} className="absolute inset-y-0 w-px bg-line-subtle" style={{ left: `${(tick / span) * 100}%` }} />
              ))}
            </div>
          </div>

          {virtualizer.getVirtualItems().map((item) => {
            const row = rows[item.index];
            const { step } = row;
            const type = metaOf(STEP_TYPE, step.type, "StepType");
            const status = metaOf(STEP_STATUS, step.status, "StepStatus");
            const TypeIcon = type.icon;
            const StatusIcon = status.icon;
            const bar = barFor(step, span, nowOffset);
            const selected = step.id === selectedId;
            const flash = focusRequest?.stepId === step.id;
            // The duration sits after the bar; before it when the bar ends near the right edge; and
            // inside it when the bar is so wide that neither side has room.
            const labelPlace = bar.left + bar.width <= 82 ? "after" : bar.left >= 16 ? "before" : "inside";
            return (
              <div
                key={step.id}
                role="treeitem"
                aria-level={row.depth + 1}
                aria-selected={selected}
                aria-expanded={row.hasChildren ? !row.collapsed : undefined}
                data-step-id={step.id}
                data-cursor={step.id === cursorId || undefined}
                data-highlighted={highlighted.has(step.id) || undefined}
                onClick={() => onSelect(step.id)}
                className={cn(
                  COLUMNS,
                  "group/row absolute inset-x-0 cursor-pointer text-13 transition-colors duration-150 ease-out hover:bg-raised/70",
                  selected && "bg-raised shadow-[inset_2px_0_0_var(--foreground)] hover:bg-raised",
                  !selected && "data-cursor:bg-raised/50 data-cursor:shadow-[inset_2px_0_0_var(--fg-subtle)]",
                  "data-highlighted:bg-timed-out/10",
                )}
                style={{ top: item.start, height: ROW_HEIGHT }}
              >
                {/* When a deep link lands here, a tint fades out over the row. */}
                {flash && <span key={focusRequest.at} aria-hidden="true" className="row-flash pointer-events-none absolute inset-0" />}

                <div className="flex min-w-0 items-center gap-1.5 border-r border-line-subtle pr-2" style={{ paddingLeft: 10 + row.depth * INDENT }}>
                  {row.hasChildren ? (
                    <button
                      type="button"
                      tabIndex={-1}
                      aria-label={`${row.collapsed ? "Expand" : "Collapse"} ${step.name}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        onToggle(step.id);
                      }}
                      className="flex size-4 shrink-0 items-center justify-center rounded-sm text-fg-subtle hover:bg-hover hover:text-fg"
                    >
                      <ChevronRight className={cn("size-3 transition-transform duration-150 ease-out", !row.collapsed && "rotate-90")} aria-hidden="true" />
                    </button>
                  ) : (
                    <span className="size-4 shrink-0" />
                  )}
                  <span title={type.label} className="shrink-0">
                    <TypeIcon className="size-3.5 text-fg-subtle" aria-hidden="true" />
                    <span className="sr-only">{type.label}</span>
                  </span>
                  <span className={cn("truncate font-mono text-xs", step.status === "failed" && "text-failed")}>{step.name}</span>
                  {row.node.attempts > 1 && (
                    <span
                      title={`Attempt ${step.attempt} of ${row.node.attempts}`}
                      className="num shrink-0 rounded-sm border border-line px-1 font-mono text-[10px] leading-4 text-fg-muted"
                    >
                      {step.attempt}/{row.node.attempts}
                    </span>
                  )}
                  {row.collapsed && (
                    <span className="num shrink-0 font-mono text-[10px] text-fg-subtle" title={`${row.node.descendantCount} steps hidden`}>
                      +{row.node.descendantCount}
                    </span>
                  )}
                  <span title={status.label} className="ml-auto shrink-0">
                    <StatusIcon
                      className={cn("size-3.5", TONE_TEXT[status.tone], status.spin && "animate-spin [animation-duration:1.4s]", step.status === "completed" && "opacity-60")}
                      aria-hidden="true"
                    />
                    <span className="sr-only">{status.label}</span>
                  </span>
                </div>

                <div className="relative mx-3">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div
                        className="absolute inset-y-0 flex items-center"
                        style={{ left: `${bar.left}%`, width: `max(2px, ${bar.width}%)` }}
                      >
                        <span className={cn("h-2.5 w-full rounded-[2px]", BAR_TONE[step.status] ?? BAR_TONE.completed)} />
                        <span
                          className={cn(
                            "num pointer-events-none absolute whitespace-nowrap font-mono text-[11px]",
                            labelPlace === "after" && "left-full ml-1.5 text-fg-subtle",
                            labelPlace === "before" && "right-full mr-1.5 text-fg-subtle",
                            labelPlace === "inside" && "right-1.5 font-medium text-background",
                          )}
                        >
                          {formatDuration(bar.durationMs)}
                          {bar.open && "…"}
                        </span>
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="flex flex-col gap-0.5">
                      <span className="font-mono">{step.name}</span>
                      <span>
                        {status.label} · {bar.open ? `running for ${formatDuration(bar.durationMs)}` : formatDuration(step.duration_ms)}
                      </span>
                      <span className="opacity-70">starts at +{formatDuration(step.offset_ms)}</span>
                    </TooltipContent>
                  </Tooltip>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
