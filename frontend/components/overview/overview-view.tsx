"use client";

/**
 * The overview: what the agents are doing, at a glance. Every number is a field of
 * `/stats/overview`, `/agents`, `/executions` or `/anomalies`; nothing is computed here beyond
 * formatting. Each panel loads, empties and fails on its own, so one slow or broken endpoint
 * never blanks the page.
 */
import { Blocks, Inbox, ShieldCheck } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { HealthBadge, SeverityBadge } from "@/components/data/badges";
import { WINDOW_LABEL, WindowSwitch, windowFrom } from "@/components/data/controls";
import { EmptyState } from "@/components/data/empty-state";
import { ErrorState, Panel, StatTile, StatTileSkeleton } from "@/components/data/states";
import { Timestamp } from "@/components/data/values";
import { COMPACT_COLUMNS, ExecutionsTable } from "@/components/executions/executions-table";
import { Page } from "@/components/shell/page";
import { Skeleton } from "@/components/ui/skeleton";
import { LIST_POLL_MS, useAgents, useAnomalies, useExecutions, useStatsOverview, useStatsTimeseries } from "@/lib/api/hooks";
import type { Agent, AgentHealth, StatsOverview, StatsWindow } from "@/lib/api/types";
import { formatCount, formatDuration, formatRate, pluralize } from "@/lib/format";
import { useUrlState } from "@/lib/use-url-state";
import { cn } from "@/lib/utils";

import { TrendChart } from "./trend-chart";

const LIVE = { refetchInterval: LIST_POLL_MS };
/** Agents that need attention come first. */
const HEALTH_ORDER: Record<AgentHealth, number> = { failing: 0, degraded: 1, healthy: 2, idle: 3 };

const SEED_COMMAND = "cd demo && uv run python seed.py";

function Tiles({ stats, window }: { stats: StatsOverview; window: StatsWindow }) {
  const finished = stats.completed + stats.failed + stats.timed_out;
  const within = `last ${WINDOW_LABEL[window]}`;
  return (
    <>
      <StatTile label="Agents" value={formatCount(stats.total_agents)} detail="registered" />
      <StatTile
        label="Executions"
        value={formatCount(stats.total_executions)}
        detail={stats.running > 0 ? `${formatCount(stats.running)} running now` : within}
      />
      <StatTile label="Completed" value={formatCount(stats.completed)} detail={within} />
      <StatTile label="Failed" value={formatCount(stats.failed)} detail={within} tone={stats.failed > 0 ? "failed" : undefined} />
      <StatTile label="Timed out" value={formatCount(stats.timed_out)} detail={within} tone={stats.timed_out > 0 ? "timed-out" : undefined} />
      <StatTile
        label="Success rate"
        value={formatRate(stats.success_rate)}
        detail={stats.success_rate === null ? "no finished runs" : `${formatCount(stats.completed)} of ${formatCount(finished)} finished`}
      />
      <StatTile label="Avg duration" value={formatDuration(stats.avg_duration_ms)} detail={stats.avg_duration_ms === null ? "no finished runs" : "finished runs"} />
      <StatTile
        label="Open anomalies"
        value={formatCount(stats.open_anomalies)}
        detail="open now, any time"
        tone={stats.open_anomalies > 0 ? "timed-out" : undefined}
      />
    </>
  );
}

function AgentRow({ agent }: { agent: Agent }) {
  const { stats } = agent;
  return (
    <li className="relative flex h-11 items-center gap-3 border-b border-line-subtle px-4 transition-colors duration-150 last:border-0 hover:bg-raised">
      <HealthBadge health={stats.health} iconOnly />
      <div className="min-w-0 flex-1">
        <Link href={`/agents/${agent.id}`} className="block truncate font-medium after:absolute after:inset-0">
          {agent.name}
        </Link>
        <p className="truncate text-xs text-fg-subtle">
          {stats.last_execution ? (
            <>
              last run <Timestamp value={stats.last_execution.started_at} />
            </>
          ) : (
            "never run"
          )}
          {stats.open_anomalies > 0 && <span className="text-timed-out"> · {pluralize(stats.open_anomalies, "open anomaly", "open anomalies")}</span>}
        </p>
      </div>
      <div className="text-right">
        <p className="num font-mono text-xs">{formatRate(stats.success_rate)}</p>
        <p className="text-[11px] text-fg-subtle">success</p>
      </div>
    </li>
  );
}

const ListSkeleton = ({ rows }: { rows: number }) => (
  <div aria-busy="true">
    {Array.from({ length: rows }, (_, index) => (
      <div key={index} className="flex h-11 items-center gap-3 border-b border-line-subtle px-4 last:border-0">
        <Skeleton className="size-3.5 rounded-full" />
        <div className="flex flex-1 flex-col gap-1.5">
          <Skeleton className="h-3 w-32" />
          <Skeleton className="h-2.5 w-20" />
        </div>
        <Skeleton className="h-3 w-10" />
      </div>
    ))}
  </div>
);

const PanelLink = ({ href, children }: { href: string; children: ReactNode }) => (
  <Link href={href} className="rounded-sm text-xs underline-offset-2 hover:text-fg hover:underline">
    {children}
  </Link>
);

export function OverviewView() {
  const [params, setParams] = useUrlState();
  const window = windowFrom(params);

  const stats = useStatsOverview(window, LIVE);
  const series = useStatsTimeseries({ window }, LIVE);
  const agents = useAgents({ limit: 200 }, LIVE);
  const recent = useExecutions({ limit: 8 }, LIVE);
  const anomalies = useAnomalies({ status: ["open"], limit: 6 }, LIVE);

  return (
    <Page
      title="Overview"
      description="What your agents are doing, and whether they are actually doing it."
      actions={<WindowSwitch value={window} onChange={(next) => setParams({ window: next === "7d" ? null : next }, "push")} />}
    >
      <section aria-label={`Totals for the last ${WINDOW_LABEL[window]}`}>
        {stats.error ? (
          <ErrorState error={stats.error} onRetry={() => void stats.refetch()} title="Totals could not be loaded" compact className="rounded-lg border border-failed/30" />
        ) : (
          <div className={cn("grid grid-cols-4 gap-3 min-[1400px]:grid-cols-8", stats.isPlaceholderData && "opacity-60")}>
            {stats.data ? <Tiles stats={stats.data} window={window} /> : Array.from({ length: 8 }, (_, index) => <StatTileSkeleton key={index} />)}
          </div>
        )}
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title={`Executions · last ${WINDOW_LABEL[window]}`} className="xl:col-span-2">
          <div className={cn("h-60", series.isPlaceholderData && "opacity-60")}>
            {series.error ? (
              <ErrorState error={series.error} onRetry={() => void series.refetch()} title="The trend could not be loaded" compact />
            ) : series.data ? (
              <TrendChart data={series.data} />
            ) : (
              <Skeleton className="h-full w-full" />
            )}
          </div>
        </Panel>

        <Panel title="Agent health" flush action={<PanelLink href="/agents">All agents</PanelLink>}>
          {agents.error ? (
            <ErrorState error={agents.error} onRetry={() => void agents.refetch()} title="Agents could not be loaded" compact />
          ) : !agents.data ? (
            <ListSkeleton rows={4} />
          ) : agents.data.items.length === 0 ? (
            <div className="p-4">
              <EmptyState icon={Blocks} title="No agents registered" description="An agent registers itself the first time it runs with the Ghostwatch SDK." command={SEED_COMMAND} />
            </div>
          ) : (
            <ul>
              {[...agents.data.items]
                .sort((a, b) => HEALTH_ORDER[a.stats.health] - HEALTH_ORDER[b.stats.health] || a.name.localeCompare(b.name))
                .map((agent) => (
                  <AgentRow key={agent.id} agent={agent} />
                ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title="Recent executions" flush className="xl:col-span-2" action={<PanelLink href="/executions">All executions</PanelLink>}>
          {recent.error ? (
            <ErrorState error={recent.error} onRetry={() => void recent.refetch()} title="Recent executions could not be loaded" compact />
          ) : (
            <ExecutionsTable
              rows={recent.data?.items}
              columns={COMPACT_COLUMNS}
              skeletonRows={8}
              caption="Recent executions"
              empty={
                <div className="p-4">
                  <EmptyState icon={Inbox} title="No executions yet" description="Runs appear here as soon as an instrumented agent reports one. To create sample history:" command={SEED_COMMAND} />
                </div>
              }
            />
          )}
        </Panel>

        <Panel
          title="Open anomalies"
          flush
          action={<PanelLink href="/anomalies">{anomalies.data ? `All ${formatCount(anomalies.data.total)} open` : "All anomalies"}</PanelLink>}
        >
          {anomalies.error ? (
            <ErrorState error={anomalies.error} onRetry={() => void anomalies.refetch()} title="Anomalies could not be loaded" compact />
          ) : !anomalies.data ? (
            <ListSkeleton rows={5} />
          ) : anomalies.data.items.length === 0 ? (
            <div className="p-4">
              <EmptyState icon={ShieldCheck} title="No open anomalies" description="No run currently breaks a detection rule. Rules run on every execution as it ends." />
            </div>
          ) : (
            <ul>
              {anomalies.data.items.map((anomaly) => (
                <li key={anomaly.id} className="relative flex min-h-11 items-center gap-3 border-b border-line-subtle px-4 py-1.5 transition-colors duration-150 last:border-0 hover:bg-raised">
                  <SeverityBadge severity={anomaly.severity} iconOnly />
                  <div className="min-w-0 flex-1">
                    <Link
                      href={anomaly.execution_id ? `/executions/${anomaly.execution_id}?anomaly=${anomaly.id}` : "/anomalies"}
                      className="block truncate after:absolute after:inset-0"
                      title={anomaly.title}
                    >
                      {anomaly.title}
                    </Link>
                    <p className="truncate text-xs text-fg-subtle">
                      {anomaly.agent_name} · <Timestamp value={anomaly.detected_at} />
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </Page>
  );
}
