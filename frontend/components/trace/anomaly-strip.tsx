"use client";

/**
 * The anomalies raised on this execution, above the waterfall. Opening one shows the rule's own
 * explanation and its evidence, and highlights the steps that evidence points at.
 */
import { ChevronRight } from "lucide-react";

import { AnomalyStatusBadge, AnomalyTypeBadge, SeverityBadge } from "@/components/data/badges";
import { EvidenceItem } from "@/components/investigation/evidence-item";
import type { Anomaly, ID } from "@/lib/api/types";
import { metaOf, SEVERITY, TONE_BORDER_LEFT } from "@/lib/enums";
import { cn } from "@/lib/utils";

/** The steps an anomaly's evidence points at. */
export const evidenceStepIds = (anomaly: Anomaly | undefined): ReadonlySet<ID> =>
  new Set((anomaly?.evidence ?? []).flatMap((item) => (item.kind === "step" && item.ref_id ? [item.ref_id] : [])));

export function AnomalyStrip({
  anomalies,
  activeId,
  onActiveChange,
}: {
  anomalies: Anomaly[];
  activeId: ID | null;
  onActiveChange: (id: ID | null) => void;
}) {
  if (anomalies.length === 0) return null;
  const ordered = [...anomalies].sort(
    (a, b) => (SEVERITY[b.severity]?.rank ?? 0) - (SEVERITY[a.severity]?.rank ?? 0) || a.detected_at.localeCompare(b.detected_at),
  );
  return (
    <section aria-label="Anomalies on this execution" className="shrink-0 px-6 pb-4">
      <ul className="flex flex-col gap-1.5">
        {ordered.map((anomaly) => {
          const open = anomaly.id === activeId;
          const tone = metaOf(SEVERITY, anomaly.severity, "Severity").tone;
          const stepCount = evidenceStepIds(anomaly).size;
          return (
            <li key={anomaly.id} className={cn("rounded-md border border-l-2 border-line-subtle bg-surface", TONE_BORDER_LEFT[tone])}>
              <button
                type="button"
                aria-expanded={open}
                onClick={() => onActiveChange(open ? null : anomaly.id)}
                className="flex min-h-9 w-full flex-wrap items-center gap-x-4 gap-y-1 rounded-md px-3 py-1.5 text-left hover:bg-raised/70"
              >
                <ChevronRight className={cn("size-3.5 shrink-0 text-fg-subtle transition-transform duration-150 ease-out", open && "rotate-90")} aria-hidden="true" />
                <SeverityBadge severity={anomaly.severity} />
                <span className="min-w-0 font-medium">{anomaly.title}</span>
                <AnomalyTypeBadge type={anomaly.type} className="text-xs" />
                <span className="ml-auto flex items-center gap-4 text-xs">
                  {anomaly.status !== "open" && <AnomalyStatusBadge status={anomaly.status} />}
                  <code className="font-mono text-fg-subtle">{anomaly.rule_id}</code>
                </span>
              </button>
              {open && (
                <div className="flex flex-col gap-3 border-t border-line-subtle px-3 py-3 pl-10">
                  <p className="max-w-4xl text-fg-muted">{anomaly.explanation}</p>
                  <div>
                    <h3 className="mb-1.5 text-xs font-medium text-fg-subtle">
                      Evidence
                      {stepCount > 0 && <span className="font-normal"> · {stepCount === 1 ? "1 step is" : `${stepCount} steps are`} highlighted below</span>}
                    </h3>
                    <div className="grid max-w-5xl gap-1.5 lg:grid-cols-2">
                      {anomaly.evidence.map((item, index) => (
                        <EvidenceItem key={index} evidence={item} executionId={anomaly.execution_id} onExecutionPage />
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
