import { FileSearch, History } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { StatusBadge } from "@/components/data/badges";
import { Cost, Duration, IdChip, Timestamp, Tokens } from "@/components/data/values";
import { Button } from "@/components/ui/button";
import type { ExecutionDetail } from "@/lib/api/types";
import { formatCount, pluralize } from "@/lib/format";

function Meta({ label, children, title }: { label: string; children: ReactNode; title?: string }) {
  return (
    <div className="flex flex-col gap-0.5" title={title}>
      <dt className="text-[11px] text-fg-subtle">{label}</dt>
      <dd className="flex h-5 items-center whitespace-nowrap">{children}</dd>
    </div>
  );
}

/** Who ran, how it ended, what it cost, and what it is a replay of. Every value is an API field. */
export function TraceHeader({ execution, live }: { execution: ExecutionDetail; live: boolean }) {
  const tokenBreakdown =
    execution.tokens_input === null && execution.tokens_output === null
      ? "No step reported token usage"
      : `${formatCount(execution.tokens_input)} in · ${formatCount(execution.tokens_output)} out`;
  return (
    <header className="flex shrink-0 flex-col gap-3 px-6 pb-4 pt-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="text-xl font-semibold tracking-tight">
              <Link href={`/agents/${execution.agent_id}`} className="rounded-sm underline-offset-4 hover:underline">
                {execution.agent_name}
              </Link>
            </h1>
            <StatusBadge status={execution.status} className="text-sm" />
            {live && (
              <span className="text-xs text-fg-subtle" aria-live="polite">
                Live · refreshing every 3 s
              </span>
            )}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-muted">
            <IdChip id={execution.id} full />
            {execution.replay_of && (
              <span className="inline-flex items-center gap-1.5">
                <History className="size-3.5" aria-hidden="true" />
                Replay of <IdChip id={execution.replay_of} href={`/executions/${execution.replay_of}`} />
              </span>
            )}
            {execution.replay_ids.length > 0 && (
              <Link
                href={`/replays?original_execution_id=${execution.id}`}
                className="inline-flex items-center gap-1.5 rounded-sm underline-offset-2 hover:text-fg hover:underline"
              >
                <History className="size-3.5" aria-hidden="true" />
                Replayed {execution.replay_ids.length}×
              </Link>
            )}
            {execution.tags.map((tag) => (
              <span key={tag} className="rounded-sm border border-line px-1.5 font-mono text-[11px] leading-4">
                {tag}
              </span>
            ))}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href={`/executions/${execution.id}?tab=investigation`}>
              <FileSearch aria-hidden="true" />
              {execution.has_investigation ? "Investigation" : "Investigate"}
            </Link>
          </Button>
          <Button variant="outline" size="sm" disabled title="Replay is not implemented yet (F10, #30)">
            <History aria-hidden="true" />
            Replay
          </Button>
        </div>
      </div>

      <dl className="flex flex-wrap gap-x-8 gap-y-2">
        <Meta label="Started">
          <Timestamp value={execution.started_at} />
        </Meta>
        <Meta label="Ended">{execution.ended_at ? <Timestamp value={execution.ended_at} /> : <span className="text-fg-subtle">Not ended</span>}</Meta>
        <Meta label="Duration">
          <Duration ms={execution.duration_ms} />
        </Meta>
        <Meta label="Steps">
          <span className="num font-mono text-xs">{formatCount(execution.step_count)}</span>
        </Meta>
        <Meta label="Tokens" title={tokenBreakdown}>
          <Tokens value={execution.tokens_total} />
        </Meta>
        <Meta label="Cost">
          <Cost usd={execution.cost_usd} />
        </Meta>
        <Meta label="Model">
          {execution.config.model ? <code className="font-mono text-xs">{execution.config.model}</code> : <span className="text-fg-subtle">—</span>}
        </Meta>
        <Meta label="Anomalies">
          <span className="num font-mono text-xs">{execution.anomaly_count === 0 ? "None" : pluralize(execution.anomaly_count, "anomaly", "anomalies")}</span>
        </Meta>
      </dl>

      {execution.error && (
        <p role="status" className="rounded-md border border-failed/30 bg-failed/5 px-3 py-2 font-mono text-xs">
          <span className="font-medium text-failed">{execution.error.type}</span>
          <span className="text-fg-subtle">: </span>
          <span className="break-words">{execution.error.message}</span>
        </p>
      )}
    </header>
  );
}
