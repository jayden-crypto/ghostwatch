/**
 * One piece of evidence (contract §2), shown the same way wherever it appears: under an anomaly,
 * under a fact, in the trace explorer.
 *
 * `observed`, `expected` and `excerpt` are copied from stored data by backend code. They are shown
 * verbatim, in mono, and every evidence item that points at a step links to that exact step.
 */
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { EvidenceKindBadge } from "@/components/data/badges";
import type { Evidence, ID, Json } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** Where an evidence item's `ref_id` leads, or null when it points at nothing openable. */
export function evidenceHref(evidence: Evidence, executionId: ID | null): string | null {
  if (!evidence.ref_id) return null;
  switch (evidence.kind) {
    case "step":
      return executionId ? `/executions/${executionId}?step=${evidence.ref_id}` : null;
    case "event":
      return executionId ? `/executions/${executionId}?tab=events&event=${evidence.ref_id}` : null;
    case "execution":
      return `/executions/${evidence.ref_id}`;
    case "anomaly":
      return `/anomalies?anomaly=${evidence.ref_id}`;
    default:
      return null;
  }
}

const LINK_LABEL: Partial<Record<Evidence["kind"], string>> = {
  step: "Open step",
  event: "Open event",
  execution: "Open execution",
  anomaly: "Open anomaly",
};

/** A stored value on one line: strings as they are, everything else as compact JSON. */
const inline = (value: Json): string => (typeof value === "string" ? value : JSON.stringify(value));

function Value({ label, value, className }: { label: string; value: Json; className?: string }) {
  return (
    <div className="flex min-w-0 items-baseline gap-2">
      <dt className="w-16 shrink-0 text-xs text-fg-subtle">{label}</dt>
      <dd className={cn("min-w-0 break-words font-mono text-xs", className)}>{inline(value)}</dd>
    </div>
  );
}

export function EvidenceItem({
  evidence,
  executionId,
  onExecutionPage = false,
  className,
}: {
  evidence: Evidence;
  /** The execution the evidence belongs to; step and event references are resolved inside it. */
  executionId: ID | null;
  /** Shown on that execution's own page, where a link to the execution itself would lead nowhere. */
  onExecutionPage?: boolean;
  className?: string;
}) {
  const self = onExecutionPage && evidence.kind === "execution" && evidence.ref_id === executionId;
  const href = self ? null : evidenceHref(evidence, executionId);
  return (
    <div className={cn("flex flex-col gap-1.5 rounded-md border border-line-subtle bg-background/40 px-3 py-2", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-baseline gap-2">
          <EvidenceKindBadge kind={evidence.kind} iconOnly className="translate-y-0.5" />
          <span className="min-w-0">{evidence.label}</span>
          {evidence.field && <code className="shrink-0 font-mono text-xs text-fg-subtle">{evidence.field}</code>}
        </div>
        {href && (
          <Link
            href={href}
            className="inline-flex shrink-0 items-center gap-1 rounded-sm text-xs text-fg-muted underline-offset-2 hover:text-fg hover:underline"
          >
            {LINK_LABEL[evidence.kind]}
            <ArrowRight className="size-3" aria-hidden="true" />
          </Link>
        )}
      </div>
      <dl className="flex flex-col gap-0.5">
        <Value label="observed" value={evidence.observed} />
        {evidence.expected !== null && <Value label="expected" value={evidence.expected} className="text-fg-muted" />}
      </dl>
      {evidence.excerpt !== null && (
        <blockquote className="max-h-40 overflow-auto whitespace-pre-wrap break-words border-l-2 border-line pl-2.5 font-mono text-xs text-fg-muted">
          {evidence.excerpt}
        </blockquote>
      )}
    </div>
  );
}
