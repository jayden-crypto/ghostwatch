"use client";

/**
 * The step inspector: everything recorded about one step. Every field of the contract's `Step`
 * appears here, under Overview, Input, Output, Error or Metadata.
 */
import { X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { StepStatusBadge, StepTypeBadge } from "@/components/data/badges";
import { JsonViewer } from "@/components/data/json-viewer";
import { CopyButton, Duration, IdChip, Timestamp, Tokens } from "@/components/data/values";
import { Button } from "@/components/ui/button";
import type { ID, Step } from "@/lib/api/types";
import { DASH, formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

export const INSPECTOR_TABS = ["overview", "input", "output", "error", "metadata"] as const;
export type InspectorTab = (typeof INSPECTOR_TABS)[number];

const TAB_LABEL: Record<InspectorTab, string> = {
  overview: "Overview",
  input: "Input",
  output: "Output",
  error: "Error",
  metadata: "Metadata",
};

const MIN_WIDTH = 320;
const MAX_WIDTH = 760;
const DEFAULT_WIDTH = 400;
const WIDTH_KEY = "ghostwatch.inspector-width";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-h-7 items-baseline gap-3 border-b border-line-subtle py-1.5 last:border-0">
      <dt className="w-28 shrink-0 text-xs text-fg-subtle">{label}</dt>
      <dd className="min-w-0 flex-1 break-words">{children}</dd>
    </div>
  );
}

const Absent = ({ children = DASH }: { children?: ReactNode }) => <span className="text-fg-subtle">{children}</span>;

function Overview({ step, attempts, onSelectStep }: { step: Step; attempts: number; onSelectStep: (id: ID) => void }) {
  return (
    <dl>
      <Field label="Status">
        <StepStatusBadge status={step.status} />
      </Field>
      <Field label="Type">
        <StepTypeBadge type={step.type} />
      </Field>
      <Field label="Step">
        <span className="num font-mono text-xs">
          #{step.ordinal}
          <span className="text-fg-subtle"> · depth {step.depth}</span>
        </span>
      </Field>
      <Field label="Attempt">
        <span className="num font-mono text-xs">
          {step.attempt}
          {attempts > 1 && <span className="text-fg-subtle"> of {attempts}</span>}
        </span>
      </Field>
      <Field label="Started">
        <Timestamp value={step.started_at} mode="utc" />
        <span className="num ml-2 font-mono text-xs text-fg-subtle">+{formatDuration(step.offset_ms)}</span>
      </Field>
      <Field label="Ended">{step.ended_at ? <Timestamp value={step.ended_at} mode="utc" /> : <Absent>Not ended</Absent>}</Field>
      <Field label="Duration">{step.duration_ms === null ? <Absent>Still running</Absent> : <Duration ms={step.duration_ms} />}</Field>
      <Field label="Tool">{step.tool_name ? <code className="font-mono text-xs">{step.tool_name}</code> : <Absent />}</Field>
      <Field label="Model">{step.model ? <code className="font-mono text-xs">{step.model}</code> : <Absent />}</Field>
      <Field label="Tokens in">
        <Tokens value={step.tokens_input} />
      </Field>
      <Field label="Tokens out">
        <Tokens value={step.tokens_output} />
      </Field>
      <Field label="Parent step">
        {step.parent_step_id ? (
          <button
            type="button"
            onClick={() => onSelectStep(step.parent_step_id!)}
            className="rounded-sm font-mono text-xs underline-offset-2 hover:underline"
            title={step.parent_step_id}
          >
            {step.parent_step_id.slice(0, 8)}…{step.parent_step_id.slice(-4)}
          </button>
        ) : (
          <Absent>None (top level)</Absent>
        )}
      </Field>
      <Field label="Step id">
        <IdChip id={step.id} full className="break-all" />
      </Field>
    </dl>
  );
}

function ErrorTab({ step }: { step: Step }) {
  if (!step.error) return <p className="text-fg-muted">This step recorded no error.</p>;
  return (
    <div className="flex flex-col gap-3">
      <div>
        <p className="font-mono text-xs font-medium text-failed">{step.error.type}</p>
        <p className="mt-1 break-words font-mono text-xs">{step.error.message}</p>
      </div>
      {step.error.stacktrace ? (
        <div className="relative">
          <CopyButton value={step.error.stacktrace} label="stack trace" className="absolute right-2 top-2" />
          <pre className="max-h-[60vh] overflow-auto rounded-md border border-line-subtle bg-surface p-3 pr-9 font-mono text-xs leading-5 text-fg-muted">
            {step.error.stacktrace}
          </pre>
        </div>
      ) : (
        <p className="text-fg-muted">No stack trace was recorded for this error.</p>
      )}
    </div>
  );
}

/** A panel width the user can drag or arrow-key, remembered across pages. */
function useResizableWidth() {
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  useEffect(() => {
    const saved = Number(window.localStorage.getItem(WIDTH_KEY));
    // Reading storage is only possible after mount, so the first paint uses the default width.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (saved >= MIN_WIDTH && saved <= MAX_WIDTH) setWidth(saved);
  }, []);
  const update = useCallback((next: number) => {
    const clamped = Math.round(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, next)));
    setWidth(clamped);
    window.localStorage.setItem(WIDTH_KEY, String(clamped));
  }, []);
  return [width, update] as const;
}

export function StepInspector({
  step,
  attempts,
  tab,
  onTabChange,
  onClose,
  onSelectStep,
}: {
  step: Step;
  /** How many attempts this step's name has under the same parent. */
  attempts: number;
  tab: InspectorTab;
  onTabChange: (tab: InspectorTab) => void;
  onClose: () => void;
  onSelectStep: (id: ID) => void;
}) {
  const [width, setWidth] = useResizableWidth();
  const drag = useRef<{ startX: number; startWidth: number } | null>(null);

  return (
    <aside
      aria-label={`Step ${step.name}`}
      data-testid="step-inspector"
      className="relative flex shrink-0 flex-col border-l border-line bg-background"
      style={{ width, maxWidth: "70%" }}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize step inspector"
        aria-valuenow={width}
        aria-valuemin={MIN_WIDTH}
        aria-valuemax={MAX_WIDTH}
        tabIndex={0}
        onPointerDown={(event) => {
          drag.current = { startX: event.clientX, startWidth: width };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          if (drag.current) setWidth(drag.current.startWidth + (drag.current.startX - event.clientX));
        }}
        onPointerUp={() => (drag.current = null)}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") setWidth(width + 24);
          if (event.key === "ArrowRight") setWidth(width - 24);
        }}
        className="absolute inset-y-0 -left-1 z-30 w-2 cursor-col-resize transition-colors duration-150 hover:bg-running/40 focus-visible:bg-running/40 focus-visible:outline-none"
      />

      <header className="flex shrink-0 items-start justify-between gap-3 px-4 pb-2 pt-3">
        <div className="min-w-0">
          <h2 className="truncate font-mono text-sm font-medium" title={step.name}>
            {step.name}
          </h2>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <StepStatusBadge status={step.status} />
            <StepTypeBadge type={step.type} />
            <Duration ms={step.duration_ms} />
          </div>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close step inspector" title="Close (Esc)">
          <X aria-hidden="true" />
        </Button>
      </header>

      <div role="tablist" aria-label="Step details" className="flex shrink-0 gap-4 border-b border-line-subtle px-4">
        {INSPECTOR_TABS.map((name) => {
          const selected = name === tab;
          const hasError = name === "error" && step.error !== null;
          return (
            <button
              key={name}
              type="button"
              role="tab"
              id={`inspector-tab-${name}`}
              aria-selected={selected}
              aria-controls="inspector-panel"
              onClick={() => onTabChange(name)}
              className={cn(
                "-mb-px flex h-8 items-center gap-1.5 border-b-2 border-transparent text-fg-muted transition-colors duration-150 hover:text-fg",
                selected && "border-fg text-fg",
              )}
            >
              {TAB_LABEL[name]}
              {hasError && <span aria-hidden="true" className="size-1.5 rounded-full bg-failed" />}
            </button>
          );
        })}
      </div>

      <div id="inspector-panel" role="tabpanel" aria-labelledby={`inspector-tab-${tab}`} className="min-h-0 flex-1 overflow-auto p-4">
        {tab === "overview" && <Overview step={step} attempts={attempts} onSelectStep={onSelectStep} />}
        {tab === "input" && <JsonViewer value={step.input} label="step input" />}
        {tab === "output" && <JsonViewer value={step.output} label="step output" />}
        {tab === "error" && <ErrorTab step={step} />}
        {tab === "metadata" && <JsonViewer value={step.metadata} label="step metadata" />}
      </div>
    </aside>
  );
}
