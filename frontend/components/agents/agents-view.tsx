"use client";

/** /agents: every registered agent with its health, success rate and latest run. */
import { Blocks, SearchX, X } from "lucide-react";

import { HealthBadge, StatusBadge } from "@/components/data/badges";
import { ChipFilter, SearchInput } from "@/components/data/controls";
import { DataTable, type Column } from "@/components/data/data-table";
import { EmptyState } from "@/components/data/empty-state";
import { ErrorState, Refreshing } from "@/components/data/states";
import { Duration, Timestamp } from "@/components/data/values";
import { Page } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { LIST_POLL_MS, useAgents } from "@/lib/api/hooks";
import { AGENT_HEALTHS, type Agent, type AgentHealth } from "@/lib/api/types";
import { AGENT_HEALTH } from "@/lib/enums";
import { formatCount, formatRate, pluralize } from "@/lib/format";
import { useUrlState } from "@/lib/use-url-state";

const COLUMNS: Column<Agent>[] = [
  {
    id: "agent",
    header: "Agent",
    cell: (agent) => (
      <span className="flex items-baseline gap-2">
        <span className="font-medium">{agent.name}</span>
        <code className="font-mono text-xs text-fg-subtle">{agent.slug}</code>
      </span>
    ),
    skeleton: "w-48",
  },
  { id: "health", header: "Health", cell: (agent) => <HealthBadge health={agent.stats.health} />, width: "w-28", skeleton: "w-16" },
  {
    id: "executions",
    header: "Executions",
    cell: (agent) => <span className="num font-mono text-xs">{formatCount(agent.stats.total_executions)}</span>,
    align: "right",
    width: "w-24",
    skeleton: "w-8",
  },
  {
    id: "success",
    header: "Success rate",
    cell: (agent) => (
      <span className={agent.stats.success_rate === null ? "num font-mono text-xs text-fg-subtle" : "num font-mono text-xs"} title="All time: completed ÷ finished">
        {formatRate(agent.stats.success_rate)}
      </span>
    ),
    align: "right",
    width: "w-28",
    skeleton: "w-10",
  },
  { id: "duration", header: "Avg duration", cell: (agent) => <Duration ms={agent.stats.avg_duration_ms} />, align: "right", width: "w-28", skeleton: "w-12", showFrom: "xl" },
  {
    id: "anomalies",
    header: <span title="Anomalies that are still open">Anomalies</span>,
    cell: (agent) => (
      <span className={agent.stats.open_anomalies > 0 ? "num font-mono text-xs text-timed-out" : "num font-mono text-xs text-fg-subtle"}>
        {formatCount(agent.stats.open_anomalies)}
      </span>
    ),
    align: "right",
    width: "w-24",
    skeleton: "w-6",
  },
  {
    id: "last",
    header: "Last run",
    cell: (agent) =>
      agent.stats.last_execution ? (
        <span className="flex items-center gap-2">
          <StatusBadge status={agent.stats.last_execution.status} iconOnly />
          <Timestamp value={agent.stats.last_execution.started_at} className="text-fg-muted" />
        </span>
      ) : (
        <span className="text-fg-subtle">Never run</span>
      ),
    width: "w-32",
    skeleton: "w-16",
  },
];

const HEALTH_OPTIONS = AGENT_HEALTHS.map((health) => ({ value: health, label: AGENT_HEALTH[health].label, tone: AGENT_HEALTH[health].tone }));

export function AgentsView() {
  const [params, setParams] = useUrlState();
  const q = params.get("q") ?? "";
  const health = (params.get("health") ?? "").split(",").filter((value): value is AgentHealth => (AGENT_HEALTHS as readonly string[]).includes(value));
  const filtered = q !== "" || health.length > 0;
  const { data, error, refetch, isFetching, isPlaceholderData } = useAgents(
    { q: q || undefined, health: health.length ? health : undefined, limit: 200 },
    { refetchInterval: LIST_POLL_MS },
  );
  const clear = () => setParams({ q: null, health: null });

  return (
    <Page
      title="Agents"
      description="Every agent that has registered with Ghostwatch. Health is computed by the backend from each agent's last 20 finished runs and its open anomalies."
      actions={
        <>
          <Refreshing active={isFetching && data !== undefined} />
          {data && <span className="num text-fg-muted">{pluralize(data.total, "agent")}</span>}
        </>
      }
    >
      <div className="overflow-hidden rounded-lg border border-line-subtle bg-surface">
        <div className="flex flex-wrap items-center gap-2 border-b border-line-subtle px-4 py-3" role="search" aria-label="Filter agents">
          <SearchInput label="Search by agent name or slug" placeholder="Name or slug" value={q} onCommit={(value) => setParams({ q: value })} />
          <ChipFilter label="Health" options={HEALTH_OPTIONS} selected={health} onChange={(next) => setParams({ health: next.join(",") })} />
          {filtered && (
            <Button variant="ghost" size="sm" onClick={clear} className="ml-auto text-fg-muted">
              <X aria-hidden="true" />
              Clear filters
            </Button>
          )}
        </div>
        {error ? (
          <ErrorState error={error} onRetry={() => void refetch()} title="Agents could not be loaded" compact />
        ) : (
          <DataTable
            columns={COLUMNS}
            rows={data?.items}
            rowKey={(agent) => agent.id}
            rowHref={(agent) => `/agents/${agent.id}`}
            rowLabel={(agent) => `Open agent ${agent.name}`}
            caption="Agents"
            stale={isPlaceholderData}
            skeletonRows={5}
            empty={
              <div className="p-6">
                {filtered ? (
                  <EmptyState
                    icon={SearchX}
                    title="No agents match these filters"
                    description="Loosen or clear the filters to see more."
                    action={
                      <Button variant="outline" size="sm" onClick={clear}>
                        Clear filters
                      </Button>
                    }
                  />
                ) : (
                  <EmptyState
                    icon={Blocks}
                    title="No agents registered"
                    description="An agent registers itself the first time it runs with the Ghostwatch SDK. To create the demo agents and some history:"
                    command="cd demo && uv run python seed.py"
                  />
                )}
              </div>
            }
          />
        )}
      </div>
    </Page>
  );
}
