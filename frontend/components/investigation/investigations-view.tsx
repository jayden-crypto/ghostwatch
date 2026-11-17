"use client";

/** /investigations: every investigation, newest first, with its verdict at a glance. */
import { FileSearch, SearchX, X } from "lucide-react";
import { useState } from "react";

import { InvestigationStatusBadge, ProviderBadge, RootCauseBadge, TriggerBadge } from "@/components/data/badges";
import { DataTable, Pagination, type Column } from "@/components/data/data-table";
import { EmptyState } from "@/components/data/empty-state";
import { ErrorState, Refreshing } from "@/components/data/states";
import { IdChip, Timestamp } from "@/components/data/values";
import { Page } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LIST_POLL_MS, useAgents, useInvestigations } from "@/lib/api/hooks";
import { INVESTIGATION_STATUSES, type Investigation, type InvestigationStatus } from "@/lib/api/types";
import { INVESTIGATION_STATUS } from "@/lib/enums";
import { pluralize } from "@/lib/format";
import { useUrlState } from "@/lib/use-url-state";

const ANY = "any";
const PAGE_SIZE = 50;

const COLUMNS: Column<Investigation>[] = [
  { id: "status", header: "Status", cell: (i) => <InvestigationStatusBadge status={i.status} />, width: "w-32", skeleton: "w-20" },
  {
    id: "verdict",
    header: "Root cause",
    cell: (i) => (i.report ? <RootCauseBadge status={i.report.root_cause.status} /> : <span className="text-fg-subtle">—</span>),
    width: "w-44",
    skeleton: "w-24",
  },
  {
    id: "summary",
    header: "Summary",
    cell: (i) => (
      <span className="block max-w-[15rem] truncate text-fg-muted xl:max-w-[24rem] min-[1400px]:max-w-[34rem]" title={i.report?.summary ?? i.error?.message}>
        {i.report ? (
          i.report.summary
        ) : i.error ? (
          <span className="font-mono text-xs">
            <span className="text-failed">{i.error.type}</span>: {i.error.message}
          </span>
        ) : (
          "No report yet"
        )}
      </span>
    ),
    skeleton: "w-64",
  },
  { id: "execution", header: "Execution", cell: (i) => <IdChip id={i.execution_id} href={`/executions/${i.execution_id}`} />, width: "w-36", skeleton: "w-24" },
  { id: "provider", header: "Hypotheses by", cell: (i) => <ProviderBadge provider={i.provider} model={i.model} />, width: "w-40", skeleton: "w-20", showFrom: "xl" },
  { id: "trigger", header: "Trigger", cell: (i) => <TriggerBadge trigger={i.trigger} />, width: "w-36", skeleton: "w-20", showFrom: "wide" },
  { id: "created", header: "Started", cell: (i) => <Timestamp value={i.created_at} className="text-fg-muted" />, width: "w-28", skeleton: "w-14" },
];

export function InvestigationsView() {
  const [params, setParams] = useUrlState();
  const statusParam = params.get("status");
  const status = (INVESTIGATION_STATUSES as readonly string[]).includes(statusParam ?? "") ? (statusParam as InvestigationStatus) : null;
  const agentId = params.get("agent_id");
  const [offset, setOffset] = useState(0);
  const filtered = status !== null || agentId !== null;

  const agents = useAgents({ limit: 200 });
  const { data, error, refetch, isFetching, isPlaceholderData } = useInvestigations(
    { status: status ?? undefined, agent_id: agentId ?? undefined, limit: PAGE_SIZE, offset },
    { refetchInterval: LIST_POLL_MS },
  );
  const change = (patch: Record<string, string | null>) => {
    setOffset(0);
    setParams(patch);
  };

  return (
    <Page
      title="Investigations"
      description="One per failed, timed-out or anomalous run. Each separates facts computed from recorded events from the hypotheses proposed to explain them."
      actions={
        <>
          <Refreshing active={isFetching && data !== undefined} />
          {data && <span className="num text-fg-muted">{pluralize(data.total, "investigation")}</span>}
        </>
      }
    >
      <div className="overflow-hidden rounded-lg border border-line-subtle bg-surface">
        <div className="flex flex-wrap items-center gap-2 border-b border-line-subtle px-4 py-3" role="search" aria-label="Filter investigations">
          <Select value={status ?? ANY} onValueChange={(next) => change({ status: next === ANY ? null : next })}>
            <SelectTrigger size="sm" aria-label="Status" className="h-7 min-w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>Status: any</SelectItem>
              {INVESTIGATION_STATUSES.map((value) => (
                <SelectItem key={value} value={value}>
                  {INVESTIGATION_STATUS[value].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={agentId ?? ANY} onValueChange={(next) => change({ agent_id: next === ANY ? null : next })}>
            <SelectTrigger size="sm" aria-label="Agent" className="h-7 min-w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>Agent: any</SelectItem>
              {agents.data?.items.map((agent) => (
                <SelectItem key={agent.id} value={agent.id}>
                  {agent.name}
                </SelectItem>
              ))}
              {agentId && !agents.data?.items.some((agent) => agent.id === agentId) && <SelectItem value={agentId}>{agentId}</SelectItem>}
            </SelectContent>
          </Select>
          {filtered && (
            <Button variant="ghost" size="sm" onClick={() => change({ status: null, agent_id: null })} className="ml-auto text-fg-muted">
              <X aria-hidden="true" />
              Clear filters
            </Button>
          )}
        </div>
        {error ? (
          <ErrorState error={error} onRetry={() => void refetch()} title="Investigations could not be loaded" compact />
        ) : (
          <>
            <DataTable
              columns={COLUMNS}
              rows={data?.items}
              rowKey={(investigation) => investigation.id}
              rowHref={(investigation) => `/investigations/${investigation.execution_id}`}
              rowLabel={(investigation) => `Open the investigation of execution ${investigation.execution_id}`}
              caption="Investigations"
              stale={isPlaceholderData}
              skeletonRows={8}
              empty={
                <div className="p-6">
                  {filtered ? (
                    <EmptyState
                      icon={SearchX}
                      title="No investigations match these filters"
                      description="Loosen or clear the filters to see more."
                      action={
                        <Button variant="outline" size="sm" onClick={() => change({ status: null, agent_id: null })}>
                          Clear filters
                        </Button>
                      }
                    />
                  ) : (
                    <EmptyState
                      icon={FileSearch}
                      title="No investigations yet"
                      description="One starts automatically when a run fails, times out, or raises a high or critical anomaly. To produce a failing run:"
                      command="cd demo && uv run python run_scenario.py schema-change"
                    />
                  )}
                </div>
              }
            />
            {data && <Pagination total={data.total} limit={data.limit} offset={data.offset} onOffsetChange={setOffset} noun="investigations" />}
          </>
        )}
      </div>
    </Page>
  );
}
