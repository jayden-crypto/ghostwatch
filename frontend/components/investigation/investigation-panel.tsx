"use client";

/**
 * The investigation of one execution, in whichever state it is in: not started, queued, running,
 * failed or completed. Used as the body of /investigations/[executionId] and as the Investigation
 * tab of the trace page.
 *
 * Starting one is `POST /investigations/{execution_id}`; after that the view polls every 2 s until
 * the status is terminal (lib/api/hooks.ts).
 */
import { FileSearch, LoaderCircle, RotateCw } from "lucide-react";
import { useEffect, useState } from "react";

import { InvestigationStatusBadge, ProviderBadge, TriggerBadge } from "@/components/data/badges";
import { EmptyState } from "@/components/data/empty-state";
import { ErrorState } from "@/components/data/states";
import { Timestamp } from "@/components/data/values";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/errors";
import { isInvestigationActive, useCreateInvestigation, useInvestigation } from "@/lib/api/hooks";
import type { ID, Investigation, Step } from "@/lib/api/types";
import { formatDuration } from "@/lib/format";

import { InvestigationReportView } from "./investigation-report";

/** Milliseconds since `since`, updated every second. Null until mounted, where "now" is not known. */
function useElapsed(since: string): number | null {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    const timer = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, []);
  return now === null ? null : Math.max(0, now - Date.parse(since));
}

function InProgress({ investigation }: { investigation: Investigation }) {
  const elapsed = useElapsed(investigation.created_at);
  return (
    <div role="status" className="flex flex-col items-center gap-3 rounded-lg border border-line px-6 py-12 text-center">
      <LoaderCircle className="size-5 animate-spin text-running [animation-duration:1.4s]" aria-hidden="true" />
      <div className="max-w-lg">
        <p className="text-sm font-medium">{investigation.status === "queued" ? "Queued" : "Investigating"}</p>
        <p className="mt-1 text-fg-muted">
          {investigation.status === "queued"
            ? "The investigation is waiting to start."
            : "Facts are being extracted from the recorded events, then hypotheses are proposed and checked against them."}
        </p>
        <p className="num mt-2 font-mono text-xs text-fg-subtle">
          {elapsed === null ? "…" : elapsed < 60_000 ? `${Math.floor(elapsed / 1000)} s elapsed` : `${formatDuration(elapsed)} elapsed`} · checking every 2 s
        </p>
      </div>
    </div>
  );
}

/** Status, trigger, provider and timing of an investigation, on one line. */
export function InvestigationMeta({ investigation }: { investigation: Investigation }) {
  const took =
    investigation.completed_at === null ? null : Math.max(0, Date.parse(investigation.completed_at) - Date.parse(investigation.created_at));
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-fg-muted">
      <InvestigationStatusBadge status={investigation.status} />
      <TriggerBadge trigger={investigation.trigger} />
      <ProviderBadge provider={investigation.provider} model={investigation.model} />
      <span>
        started <Timestamp value={investigation.created_at} />
      </span>
      {took !== null && <span className="num font-mono">took {formatDuration(took)}</span>}
    </div>
  );
}

export function InvestigationPanel({ executionId, steps }: { executionId: ID; steps?: Step[] }) {
  const { data: investigation, error, refetch } = useInvestigation(executionId);
  const create = useCreateInvestigation(executionId);

  if (error) return <ErrorState error={error} onRetry={() => void refetch()} title="The investigation could not be loaded" />;
  if (investigation === undefined) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading investigation">
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-40 w-full rounded-lg" />
      </div>
    );
  }

  const startError = create.error && (
    <p role="alert" className="max-w-lg text-xs text-failed">
      The investigation could not be started: {errorMessage(create.error)}
    </p>
  );

  if (investigation === null) {
    return (
      <EmptyState
        icon={FileSearch}
        title="This execution has not been investigated"
        description="Investigations start automatically when a run fails, times out, or raises a high or critical anomaly. You can start one for any finished run."
        action={
          <>
            <Button variant="outline" size="sm" disabled={create.isPending} onClick={() => create.mutate({})}>
              <FileSearch aria-hidden="true" />
              {create.isPending ? "Starting…" : "Investigate"}
            </Button>
            {startError}
          </>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <InvestigationMeta investigation={investigation} />
        {!isInvestigationActive(investigation) && (
          <Button variant="outline" size="sm" disabled={create.isPending} onClick={() => create.mutate({ force: true })}>
            <RotateCw aria-hidden="true" />
            {create.isPending ? "Starting…" : "Run again"}
          </Button>
        )}
      </div>
      {startError}

      {isInvestigationActive(investigation) && <InProgress investigation={investigation} />}

      {investigation.status === "failed" && (
        <div role="alert" className="flex flex-col gap-1 rounded-lg border border-failed/30 px-4 py-3">
          <p className="text-sm font-medium">The investigation failed</p>
          <p className="text-fg-muted">
            {investigation.error ? (
              <>
                <code className="font-mono text-xs text-failed">{investigation.error.type}</code>: {investigation.error.message}
              </>
            ) : (
              "No error was recorded."
            )}
          </p>
          <p className="text-xs text-fg-subtle">This is a failure of the investigation itself, not a finding about the execution. Use Run again to retry.</p>
        </div>
      )}

      {investigation.status === "completed" &&
        (investigation.report ? (
          <InvestigationReportView investigation={investigation} report={investigation.report} steps={steps} />
        ) : (
          // The contract says a completed investigation always has a report; say so if one does not.
          <ErrorState error={new Error("The investigation is completed but the API returned no report.")} title="The report is missing" />
        ))}
    </div>
  );
}
