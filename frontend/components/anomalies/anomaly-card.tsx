"use client";

/**
 * One anomaly, in full: what rule fired, why (the rule's own explanation, verbatim), and the
 * evidence it points at. Used on /anomalies and on an agent's page.
 *
 * Anomalies come from deterministic rules. Nothing on this card is generated or summarised.
 */
import { ArrowRight, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AnomalyStatusBadge, AnomalyTypeBadge, SeverityBadge } from "@/components/data/badges";
import { Timestamp } from "@/components/data/values";
import { EvidenceItem } from "@/components/investigation/evidence-item";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api/errors";
import { useUpdateAnomaly } from "@/lib/api/hooks";
import type { Anomaly, AnomalyStatus } from "@/lib/api/types";
import { metaOf, SEVERITY, TONE_BORDER_LEFT } from "@/lib/enums";
import { pluralize } from "@/lib/format";
import { cn } from "@/lib/utils";

/** What a person can do with an anomaly in each status. Any status may follow any other. */
const ACTIONS: Record<AnomalyStatus, { to: AnomalyStatus; label: string }[]> = {
  open: [
    { to: "acknowledged", label: "Acknowledge" },
    { to: "resolved", label: "Resolve" },
  ],
  acknowledged: [
    { to: "resolved", label: "Resolve" },
    { to: "open", label: "Reopen" },
  ],
  resolved: [{ to: "open", label: "Reopen" }],
};

export function AnomalyCard({
  anomaly,
  defaultOpen = false,
  focused = false,
  showAgent = true,
}: {
  anomaly: Anomaly;
  /** Start with the evidence showing. */
  defaultOpen?: boolean;
  /** The anomaly a link pointed at: outlined, and its evidence starts open. */
  focused?: boolean;
  showAgent?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen || focused);
  const update = useUpdateAnomaly();
  const tone = metaOf(SEVERITY, anomaly.severity, "Severity").tone;

  return (
    <article
      id={anomaly.id}
      aria-labelledby={`${anomaly.id}-title`}
      className={cn(
        "scroll-mt-4 rounded-lg border border-l-2 border-line-subtle bg-surface",
        TONE_BORDER_LEFT[tone],
        focused && "outline outline-1 outline-offset-2 outline-fg-subtle",
        anomaly.status === "resolved" && "opacity-75",
      )}
    >
      <div className="flex flex-col gap-2 px-4 py-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <SeverityBadge severity={anomaly.severity} />
          <h3 id={`${anomaly.id}-title`} className="min-w-0 text-sm font-medium">
            {anomaly.title}
          </h3>
          <AnomalyTypeBadge type={anomaly.type} className="text-xs" />
          <span className="ml-auto flex items-center gap-4 text-xs text-fg-muted">
            <AnomalyStatusBadge status={anomaly.status} />
            <Timestamp value={anomaly.detected_at} />
          </span>
        </div>

        <p className="max-w-4xl text-fg-muted">{anomaly.explanation}</p>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-fg-muted">
          {showAgent && (
            <Link href={`/agents/${anomaly.agent_id}`} className="rounded-sm underline-offset-2 hover:text-fg hover:underline">
              {anomaly.agent_name}
            </Link>
          )}
          {anomaly.execution_id && (
            <Link
              href={`/executions/${anomaly.execution_id}?anomaly=${anomaly.id}`}
              className="inline-flex items-center gap-1 rounded-sm underline-offset-2 hover:text-fg hover:underline"
            >
              Open execution
              <ArrowRight className="size-3" aria-hidden="true" />
            </Link>
          )}
          <code className="font-mono text-fg-subtle" title="The rule that raised this anomaly">
            {anomaly.rule_id}
          </code>
          <span className="ml-auto flex items-center gap-1.5">
            {ACTIONS[anomaly.status]?.map((action) => (
              <Button
                key={action.to}
                variant="outline"
                size="xs"
                disabled={update.isPending}
                onClick={() => update.mutate({ id: anomaly.id, status: action.to })}
              >
                {action.label}
              </Button>
            ))}
          </span>
        </div>
        {update.error && (
          <p role="alert" className="text-xs text-failed">
            The status could not be changed: {errorMessage(update.error)}
          </p>
        )}
      </div>

      <div className="border-t border-line-subtle">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
          className="flex h-8 w-full items-center gap-1.5 rounded-b-lg px-4 text-xs text-fg-muted hover:bg-raised/70 hover:text-fg"
        >
          <ChevronRight className={cn("size-3.5 transition-transform duration-150 ease-out", open && "rotate-90")} aria-hidden="true" />
          Evidence · {pluralize(anomaly.evidence.length, "item")}
        </button>
        {open && (
          <div className="grid gap-1.5 px-4 pb-3 xl:grid-cols-2">
            {anomaly.evidence.map((item, index) => (
              <EvidenceItem key={index} evidence={item} executionId={anomaly.execution_id} />
            ))}
          </div>
        )}
      </div>
    </article>
  );
}
