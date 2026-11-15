"use client";

/**
 * The trace explorer for one execution: header, anomalies, then the waterfall with its step
 * inspector, the raw event log, or the execution's own input and output.
 *
 * All view state is in the URL: `?step=` (selected step), `?tab=` (waterfall | events | io | investigation),
 * `?detail=` (inspector tab), `?anomaly=` (open anomaly) and `?event=` (focused raw event).
 */
import { Ghost, SearchX } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { EmptyState } from "@/components/data/empty-state";
import { JsonViewer } from "@/components/data/json-viewer";
import { ErrorState, Panel } from "@/components/data/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isNotFound } from "@/lib/api/errors";
import { useTrace } from "@/lib/api/hooks";
import type { ID, Trace } from "@/lib/api/types";
import { formatCount } from "@/lib/format";
import { traceSpan } from "@/lib/trace/layout";
import { buildTree, reveal, visibleRows } from "@/lib/trace/tree";
import { useUrlState } from "@/lib/use-url-state";
import { cn } from "@/lib/utils";

import { InvestigationPanel } from "@/components/investigation/investigation-panel";

import { AnomalyStrip, evidenceStepIds } from "./anomaly-strip";
import { RawEvents } from "./raw-events";
import { INSPECTOR_TABS, StepInspector, type InspectorTab } from "./step-inspector";
import { TraceHeader } from "./trace-header";
import { Waterfall } from "./waterfall";

const TABS = ["waterfall", "events", "io", "investigation"] as const;
type Tab = (typeof TABS)[number];

const oneOf = <T extends string>(values: readonly T[], value: string | null, fallback: T): T =>
  (values as readonly string[]).includes(value ?? "") ? (value as T) : fallback;

/** The current time, ticking four times a second while `active`; frozen otherwise. */
function useTicker(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

const isTyping = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

export function TraceSkeleton() {
  return (
    <div className="flex h-full flex-col" aria-busy="true" aria-label="Loading trace">
      <div className="flex flex-col gap-4 px-6 pb-4 pt-5">
        <div className="flex items-center gap-3">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-20" />
        </div>
        <Skeleton className="h-3 w-72" />
        <div className="flex gap-8">
          {Array.from({ length: 7 }, (_, index) => (
            <div key={index} className="flex flex-col gap-1.5">
              <Skeleton className="h-2.5 w-12" />
              <Skeleton className="h-3.5 w-16" />
            </div>
          ))}
        </div>
      </div>
      <div className="h-9 border-b border-line-subtle" />
      <div className="h-8 border-b border-line-subtle" />
      {Array.from({ length: 8 }, (_, index) => (
        <div key={index} className="grid h-7 grid-cols-[minmax(180px,36%)_minmax(0,1fr)] items-center">
          <div className="pl-8">
            <Skeleton className="h-3" style={{ width: 90 + ((index * 37) % 80) }} />
          </div>
          <div className="px-3">
            <Skeleton className="h-2.5" style={{ marginLeft: `${(index * 11) % 60}%`, width: `${12 + ((index * 17) % 25)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function TraceBody({ trace, executionId }: { trace: Trace; executionId: ID }) {
  const [params, setParams] = useUrlState();
  const { execution, steps, anomalies } = trace;
  const running = execution.status === "running";
  const now = useTicker(running);

  const tab = oneOf(TABS, params.get("tab"), "waterfall");
  const detail = oneOf(INSPECTOR_TABS, params.get("detail"), "overview");
  const stepParam = params.get("step");
  const anomalyParam = params.get("anomaly");

  const tree = useMemo(() => buildTree(steps), [steps]);
  const [collapsed, setCollapsed] = useState<ReadonlySet<ID>>(new Set());
  const [cursorId, setCursorState] = useState<ID | null>(null);
  // Keys can arrive faster than React re-renders (a held j), so the key handler reads the cursor
  // from this ref, which is updated the moment the cursor moves.
  const cursorRef = useRef<ID | null>(null);
  const setCursorId = useCallback((id: ID | null) => {
    cursorRef.current = id;
    setCursorState(id);
  }, []);
  const [focusRequest, setFocusRequest] = useState<{ stepId: ID; at: number } | null>(null);

  const selected = stepParam ? (tree.byId.get(stepParam) ?? null) : null;
  // A selected step is always visible: its ancestors are opened whatever was collapsed by hand.
  const effectiveCollapsed = useMemo(() => (selected ? reveal(tree, collapsed, selected.step.id) : collapsed), [tree, collapsed, selected]);
  const rows = useMemo(() => visibleRows(tree, effectiveCollapsed), [tree, effectiveCollapsed]);

  const span = traceSpan(execution, steps, now);
  const nowOffset = now - Date.parse(execution.started_at);
  const activeAnomaly = anomalies.find((anomaly) => anomaly.id === anomalyParam);
  const highlighted = useMemo(() => evidenceStepIds(activeAnomaly), [activeAnomaly]);

  // When the URL names a step (a deep link, an evidence link, the back button), bring it into view.
  const selectedStepId = selected?.step.id ?? null;
  useEffect(() => {
    if (selectedStepId === null) return;
    // This reacts to the URL, which is outside React: the cursor and the scroll target follow it.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCursorId(selectedStepId);
    setFocusRequest({ stepId: selectedStepId, at: Date.now() });
  }, [selectedStepId, setCursorId]);

  const selectStep = useCallback((stepId: ID | null) => setParams({ step: stepId, tab: null }), [setParams]);
  const toggle = useCallback(
    (stepId: ID) =>
      setCollapsed((current) => {
        const next = new Set(current);
        if (!next.delete(stepId)) next.add(stepId);
        return next;
      }),
    [setCollapsed],
  );

  // j / k (and the arrow keys) move through steps, Enter inspects, Esc closes.
  useEffect(() => {
    if (tab !== "waterfall") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      if (document.querySelector('[role="dialog"]')) return;
      const cursor = cursorRef.current;
      const index = cursor === null ? -1 : rows.findIndex((row) => row.step.id === cursor);
      // The URL is the source of truth for whether the inspector is open, and it updates synchronously.
      const inspecting = new URLSearchParams(window.location.search).has("step");
      const moveTo = (nextIndex: number) => {
        const row = rows[Math.min(rows.length - 1, Math.max(0, nextIndex))];
        if (!row) return;
        event.preventDefault();
        setCursorId(row.step.id);
        // With the inspector open, it follows the cursor.
        if (inspecting) setParams({ step: row.step.id });
      };
      switch (event.key) {
        case "j":
        case "ArrowDown":
          return moveTo(index + 1);
        case "k":
        case "ArrowUp":
          return moveTo(index === -1 ? 0 : index - 1);
        case "Enter":
          if (cursor !== null && !(event.target instanceof HTMLButtonElement) && !(event.target instanceof HTMLAnchorElement)) {
            event.preventDefault();
            setParams({ step: cursor });
          }
          return;
        case "ArrowRight":
        case "ArrowLeft": {
          const row = rows[index];
          if (row?.hasChildren && row.collapsed === (event.key === "ArrowRight")) {
            event.preventDefault();
            toggle(row.step.id);
          }
          return;
        }
        case "Escape":
          if (inspecting) setParams({ step: null, detail: null });
          return;
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [tab, rows, setCursorId, setParams, toggle]);

  const tabs: [Tab, string, number | null][] = [
    ["waterfall", "Waterfall", execution.step_count],
    ["events", "Raw events", trace.event_count],
    ["io", "Input & output", null],
    ["investigation", "Investigation", null],
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <TraceHeader execution={execution} live={running} />
      <AnomalyStrip anomalies={anomalies} activeId={activeAnomaly?.id ?? null} onActiveChange={(id) => setParams({ anomaly: id })} />

      <div role="tablist" aria-label="Execution views" className="flex shrink-0 items-center gap-5 border-b border-line-subtle px-6">
        {tabs.map(([name, label, count]) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={tab === name}
            onClick={() => setParams({ tab: name === "waterfall" ? null : name, event: null }, "push")}
            className={cn(
              "-mb-px flex h-9 items-center gap-1.5 border-b-2 border-transparent text-fg-muted transition-colors duration-150 hover:text-fg",
              tab === name && "border-fg text-fg",
            )}
          >
            {label}
            {count !== null && <span className="num font-mono text-xs text-fg-subtle">{formatCount(count)}</span>}
          </button>
        ))}
        {tab === "waterfall" && steps.length > 0 && (
          <span className="ml-auto hidden text-xs text-fg-subtle lg:block">
            <kbd className="font-mono">j</kbd> / <kbd className="font-mono">k</kbd> move · <kbd className="font-mono">Enter</kbd> inspect ·{" "}
            <kbd className="font-mono">Esc</kbd> close
          </span>
        )}
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1" role="tabpanel">
          {tab === "waterfall" &&
            (steps.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  icon={Ghost}
                  title="No steps were recorded for this execution"
                  description={
                    execution.status === "running"
                      ? "The execution has started but has not reported a step yet."
                      : `The execution ended with status ${execution.status} without recording a single step. That absence is itself evidence: whatever the agent reports, there is no record of it doing any work.`
                  }
                />
              </div>
            ) : (
              <Waterfall
                rows={rows}
                span={span}
                nowOffset={nowOffset}
                selectedId={selectedStepId}
                cursorId={cursorId}
                highlighted={highlighted}
                onSelect={(stepId) => {
                  setCursorId(stepId);
                  selectStep(stepId);
                }}
                onToggle={toggle}
                focusRequest={focusRequest}
              />
            ))}
          {tab === "events" && (
            <RawEvents executionId={executionId} focusedEventId={params.get("event")} onOpenStep={(stepId) => setParams({ tab: null, event: null, step: stepId }, "push")} />
          )}
          {tab === "investigation" && (
            <div className="h-full overflow-auto p-6">
              <InvestigationPanel executionId={executionId} steps={steps} />
            </div>
          )}
          {tab === "io" && (
            <div className="grid h-full content-start gap-4 overflow-auto p-6 xl:grid-cols-2">
              <Panel title="Input">
                <JsonViewer value={execution.input} label="execution input" />
              </Panel>
              <Panel title="Output">
                <JsonViewer value={execution.output} label="execution output" />
              </Panel>
              <Panel title="Config" className="xl:col-span-2">
                <JsonViewer value={execution.config} label="execution config" />
              </Panel>
            </div>
          )}
        </div>
        {tab === "waterfall" && selected && (
          <StepInspector
            step={selected.step}
            attempts={selected.attempts}
            tab={detail}
            onTabChange={(next: InspectorTab) => setParams({ detail: next === "overview" ? null : next })}
            onClose={() => setParams({ step: null, detail: null })}
            onSelectStep={(stepId) => selectStep(stepId)}
          />
        )}
      </div>
    </div>
  );
}

export function TraceView({ executionId }: { executionId: ID }) {
  const { data, error, refetch } = useTrace(executionId);
  if (error) {
    return (
      <div className="p-6">
        {isNotFound(error) ? (
          <EmptyState
            icon={SearchX}
            title="This execution does not exist"
            description={error.message}
            action={
              <Button asChild variant="outline" size="sm">
                <Link href="/executions">All executions</Link>
              </Button>
            }
          />
        ) : (
          <ErrorState error={error} onRetry={() => void refetch()} title="This trace could not be loaded" />
        )}
      </div>
    );
  }
  if (!data) return <TraceSkeleton />;
  return <TraceBody trace={data} executionId={executionId} />;
}
