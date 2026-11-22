"use client";

/**
 * /agents/[id]: one agent. Its numbers are the `stats` the API returns for it; its trend,
 * executions and anomalies are the same endpoints the rest of the app uses, filtered by agent.
 */
import { Inbox, SearchX, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { AnomalyCard } from "@/components/anomalies/anomaly-card";
import { HealthBadge } from "@/components/data/badges";
import { WINDOW_LABEL, WindowSwitch, windowFrom } from "@/components/data/controls";
import { EmptyState } from "@/components/data/empty-state";
import { JsonViewer } from "@/components/data/json-viewer";
import { ErrorState, Panel, StatTile, StatTileSkeleton } from "@/components/data/states";
import { IdChip, Timestamp } from "@/components/data/values";
import { ExecutionsTable } from "@/components/executions/executions-table";
import { TrendChart } from "@/components/overview/trend-chart";
import { Page } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isNotFound } from "@/lib/api/errors";
import { LIST_POLL_MS, useAgent, useAnomalies, useExecutions, useStatsTimeseries } from "@/lib/api/hooks";
import type { Agent, ID } from "@/lib/api/types";
import { AGENT_HEALTH, EXECUTION_STATUS, metaOf } from "@/lib/enums";
import { formatCount, formatDuration, formatRate, pluralize } from "@/lib/format";
import { useUrlState } from "@/lib/use-url-state";
import { cn } from "@/lib/utils";

const LIVE = { refetchInterval: LIST_POLL_MS };
const RECENT = 10;
const STATUS_RANK = { open: 0, acknowledged: 1, resolved: 2 } as const;

function Tiles({ agent }: { agent: Agent }) {
  const { stats } = agent;
  const finished = stats.completed + stats.failed + stats.timed_out;
  return (
    <>
      <StatTile label="Executions" value={formatCount(stats.total_executions)} detail={stats.running > 0 ? `${formatCount(stats.running)} running now` : "all time"} />
      <StatTile label="Completed" value={formatCount(stats.completed)} detail="all time" />
      <StatTile label="Failed" value={formatCount(stats.failed)} detail="all time" tone={stats.failed > 0 ? "failed" : undefined} />
      <StatTile label="Timed out" value={formatCount(stats.timed_out)} detail="all time" tone={stats.timed_out > 0 ? "timed-out" : undefined} />
      <StatTile
        label="Success rate"
        value={formatRate(stats.success_rate)}
        detail={stats.success_rate === null ? "no finished runs" : `${formatCount(stats.completed)} of ${formatCount(finished)} finished`}
      />
      <StatTile label="Avg duration" value={formatDuration(stats.avg_duration_ms)} detail={stats.avg_duration_ms === null ? "no finished runs" : "finished runs"} />
      <StatTile label="Open anomalies" value={formatCount(stats.open_anomalies)} detail="open now" tone={stats.open_anomalies > 0 ? "timed-out" : undefined} />
      <StatTile
        label="Last run"
        value={stats.last_execution ? <Timestamp value={stats.last_execution.started_at} className="font-sans text-base" /> : "—"}
        detail={stats.last_execution ? metaOf(EXECUTION_STATUS, stats.last_execution.status, "ExecutionStatus").label : "never run"}
      />
    </>
  );
}

/**
 * The page's body. The id comes from the URL on the client, so the server never streams this page's body. React reveals streamed
 * content on an animation frame, and a window that is not on screen draws none: the page would stay empty and
 * never fetch until shown.
 */
export function AgentRoute() {
  const { id } = useParams<{ id: string }>();
  return <AgentView agentId={id} />;
}

export function AgentView({ agentId }: { agentId: ID }) {
  const [params, setParams] = useUrlState();
  const window = windowFrom(params);
  const agent = useAgent(agentId);
  const series = useStatsTimeseries({ window, agent_id: agentId }, LIVE);
  const executions = useExecutions({ agent_id: agentId, limit: RECENT }, LIVE);
  const anomalies = useAnomalies({ agent_id: agentId, limit: 50 }, LIVE);

  if (agent.error) {
    return (
      <div className="p-6">
        {isNotFound(agent.error) ? (
          <EmptyState
            icon={SearchX}
            title="This agent does not exist"
            description={agent.error.message}
            action={
              <Button asChild variant="outline" size="sm">
                <Link href="/agents">All agents</Link>
              </Button>
            }
          />
        ) : (
          <ErrorState error={agent.error} onRetry={() => void agent.refetch()} title="This agent could not be loaded" />
        )}
      </div>
    );
  }

  const data = agent.data;
  const health = data && AGENT_HEALTH[data.stats.health];
  const sorted = anomalies.data && [...anomalies.data.items].sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || b.detected_at.localeCompare(a.detected_at));

  return (
    <Page
      title={
        data ? (
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {data.name}
            <HealthBadge health={data.stats.health} className="text-sm font-normal" />
          </span>
        ) : (
          <Skeleton className="h-7 w-56" />
        )
      }
      description={
        data ? (
          <span className="flex flex-col gap-1.5">
            {data.description && <span className="text-fg">{data.description}</span>}
            <span className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
              <code className="font-mono">{data.slug}</code>
              <IdChip id={data.id} />
              {data.framework && <span>framework {data.framework}</span>}
              <span>
                registered <Timestamp value={data.created_at} />
              </span>
            </span>
            {health?.hint && (
              <span className="text-xs text-fg-subtle">
                {health.label}: {health.hint.charAt(0).toLowerCase()}
                {health.hint.slice(1)}
              </span>
            )}
          </span>
        ) : (
          <Skeleton className="h-4 w-80" />
        )
      }
      actions={<WindowSwitch value={window} onChange={(next) => setParams({ window: next === "7d" ? null : next }, "push")} />}
    >
      <section aria-label="Totals for this agent" className="grid grid-cols-4 gap-3 min-[1400px]:grid-cols-8">
        {data ? <Tiles agent={data} /> : Array.from({ length: 8 }, (_, index) => <StatTileSkeleton key={index} />)}
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title={`Executions · last ${WINDOW_LABEL[window]}`} className="xl:col-span-2">
          <div className={cn("h-52", series.isPlaceholderData && "opacity-60")}>
            {series.error ? (
              <ErrorState error={series.error} onRetry={() => void series.refetch()} title="The trend could not be loaded" compact />
            ) : series.data ? (
              <TrendChart data={series.data} />
            ) : (
              <Skeleton className="h-full w-full" />
            )}
          </div>
        </Panel>
        <Panel title="Metadata">
          {data ? (
            Object.keys(data.metadata).length > 0 ? (
              <JsonViewer value={data.metadata} label="agent metadata" />
            ) : (
              <p className="text-fg-muted">This agent registered without metadata.</p>
            )
          ) : (
            <Skeleton className="h-20 w-full" />
          )}
        </Panel>
      </div>

      <Panel
        title="Recent executions"
        flush
        action={
          <Link href={`/executions?agent_id=${agentId}`} className="rounded-sm text-xs underline-offset-2 hover:text-fg hover:underline">
            {executions.data ? `All ${formatCount(executions.data.total)}` : "All executions"}
          </Link>
        }
      >
        {executions.error ? (
          <ErrorState error={executions.error} onRetry={() => void executions.refetch()} title="Executions could not be loaded" compact />
        ) : (
          <ExecutionsTable
            rows={executions.data?.items}
            columns={["status", "id", "error", "started", "duration", "steps", "tokens", "cost", "flags"]}
            skeletonRows={5}
            caption="Recent executions of this agent"
            empty={
              <div className="p-4">
                <EmptyState icon={Inbox} title="This agent has never run" description="Its executions appear here as soon as it reports one." />
              </div>
            }
          />
        )}
      </Panel>

      <section aria-labelledby="agent-anomalies" className="flex flex-col gap-3">
        <h2 id="agent-anomalies" className="text-13 font-medium">
          Anomalies
          {anomalies.data && <span className="ml-2 font-normal text-fg-subtle">{pluralize(anomalies.data.total, "anomaly", "anomalies")}</span>}
        </h2>
        {anomalies.error ? (
          <ErrorState error={anomalies.error} onRetry={() => void anomalies.refetch()} title="Anomalies could not be loaded" />
        ) : !sorted ? (
          <Skeleton className="h-28 w-full rounded-lg" />
        ) : sorted.length === 0 ? (
          <EmptyState icon={ShieldCheck} title="No anomalies for this agent" description="None of its runs has broken a detection rule. Rules run on every execution as it ends." />
        ) : (
          sorted.map((anomaly) => <AnomalyCard key={anomaly.id} anomaly={anomaly} showAgent={false} />)
        )}
      </section>
    </Page>
  );
}
