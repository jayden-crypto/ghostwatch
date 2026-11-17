"use client";

/**
 * /executions: every run of every agent, filtered, sorted and paged by the API.
 * Every control writes to the URL (lib/executions/filters.ts), so the view is always a link.
 */
import { Inbox, SearchX, X } from "lucide-react";
import { useState, type ReactNode } from "react";

import { ChipFilter, CONTROL, DebouncedInput, SearchInput } from "@/components/data/controls";
import { Pagination } from "@/components/data/data-table";
import { EmptyState } from "@/components/data/empty-state";
import { ErrorState, Refreshing } from "@/components/data/states";
import { Page } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LIST_POLL_MS, useAgents, useExecutions } from "@/lib/api/hooks";
import { EXECUTION_STATUSES } from "@/lib/api/types";
import { EXECUTION_STATUS } from "@/lib/enums";
import { activeFilterCount, CLEARED, parseFilters, RANGE_LABEL, RANGES, toListParams, type ExecutionFilters, type Range } from "@/lib/executions/filters";
import { pluralize } from "@/lib/format";
import { useNow } from "@/lib/use-now";
import { useUrlState, type UrlPatch } from "@/lib/use-url-state";
import { cn } from "@/lib/utils";

import { ExecutionsTable } from "./executions-table";

const ANY = "any";

function Labelled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-fg-subtle">
      {label}
      {children}
    </label>
  );
}

function TriState({ label, value, yes, no, onChange }: { label: string; value: boolean | null; yes: string; no: string; onChange: (value: string | null) => void }) {
  return (
    <Select value={value === null ? ANY : String(value)} onValueChange={(next) => onChange(next === ANY ? null : next)}>
      <SelectTrigger size="sm" aria-label={label} className="h-7 min-w-32">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ANY}>{label}: any</SelectItem>
        <SelectItem value="true">{yes}</SelectItem>
        <SelectItem value="false">{no}</SelectItem>
      </SelectContent>
    </Select>
  );
}

/** Seconds in the field, milliseconds in the URL (the contract's unit). */
const secondsToMs = (text: string): string | null => {
  const seconds = Number(text);
  return text.trim() === "" || Number.isNaN(seconds) || seconds < 0 ? null : String(Math.round(seconds * 1000));
};
const msToSeconds = (ms: number | null): string => (ms === null ? "" : String(ms / 1000));

/** `datetime-local` shows local time; the URL and the API carry UTC. */
const toLocalInput = (iso: string | null): string => {
  if (!iso) return "";
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
};
const fromLocalInput = (local: string): string | null => (local ? new Date(local).toISOString() : null);

function Filters({ filters, set }: { filters: ExecutionFilters; set: (patch: UrlPatch) => void }) {
  const agents = useAgents({ limit: 200 });
  // Any filter change returns to the first page.
  const update = (patch: UrlPatch) => set({ ...patch, offset: null });
  const custom = filters.range === null && (filters.started_after !== null || filters.started_before !== null);
  const [showCustom, setShowCustom] = useState(custom);
  const active = activeFilterCount(filters);

  return (
    <div className="flex flex-col gap-2 border-b border-line-subtle px-4 py-3" role="search" aria-label="Filter executions">
      <div className="flex flex-wrap items-center gap-2">
        <SearchInput label="Search by execution id or agent name" placeholder="Execution id or agent name" value={filters.q} onCommit={(q) => update({ q })} />

        <Select value={filters.agent_id ?? ANY} onValueChange={(next) => update({ agent_id: next === ANY ? null : next })}>
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
            {/* An agent named in the URL that the list does not (yet) contain is still shown as selected. */}
            {filters.agent_id && !agents.data?.items.some((agent) => agent.id === filters.agent_id) && (
              <SelectItem value={filters.agent_id}>{filters.agent_id}</SelectItem>
            )}
          </SelectContent>
        </Select>

        <ChipFilter
          label="Status"
          options={EXECUTION_STATUSES.map((status) => ({ value: status, label: EXECUTION_STATUS[status].label, tone: EXECUTION_STATUS[status].tone }))}
          selected={filters.status}
          onChange={(status) => update({ status: status.join(",") })}
        />

        {active > 0 && (
          <Button variant="ghost" size="sm" onClick={() => set(CLEARED)} className="ml-auto text-fg-muted">
            <X aria-hidden="true" />
            Clear {pluralize(active, "filter")}
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Select
          value={filters.range ?? (custom || showCustom ? "custom" : ANY)}
          onValueChange={(next) => {
            setShowCustom(next === "custom");
            if (next === "custom") update({ range: null });
            else update({ range: next === ANY ? null : next, started_after: null, started_before: null });
          }}
        >
          <SelectTrigger size="sm" aria-label="Started" className="h-7 min-w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Started: any time</SelectItem>
            {(Object.keys(RANGES) as Range[]).map((range) => (
              <SelectItem key={range} value={range}>
                {RANGE_LABEL[range]}
              </SelectItem>
            ))}
            <SelectItem value="custom">Custom range…</SelectItem>
          </SelectContent>
        </Select>
        {(custom || showCustom) && filters.range === null && (
          <>
            <Labelled label="from">
              <input
                type="datetime-local"
                value={toLocalInput(filters.started_after)}
                onChange={(event) => update({ started_after: fromLocalInput(event.target.value) })}
                className={cn(CONTROL, "[color-scheme:dark]")}
              />
            </Labelled>
            <Labelled label="before">
              <input
                type="datetime-local"
                value={toLocalInput(filters.started_before)}
                onChange={(event) => update({ started_before: fromLocalInput(event.target.value) })}
                className={cn(CONTROL, "[color-scheme:dark]")}
              />
            </Labelled>
          </>
        )}

        <Labelled label="Duration ≥">
          <DebouncedInput
            type="number"
            min={0}
            step="any"
            inputMode="decimal"
            aria-label="Minimum duration in seconds"
            placeholder="s"
            value={msToSeconds(filters.min_duration_ms)}
            onCommit={(text) => update({ min_duration_ms: secondsToMs(text) })}
            className="num w-16 font-mono text-xs"
          />
        </Labelled>
        <Labelled label="≤">
          <DebouncedInput
            type="number"
            min={0}
            step="any"
            inputMode="decimal"
            aria-label="Maximum duration in seconds"
            placeholder="s"
            value={msToSeconds(filters.max_duration_ms)}
            onCommit={(text) => update({ max_duration_ms: secondsToMs(text) })}
            className="num w-16 font-mono text-xs"
          />
        </Labelled>

        <TriState label="Anomalies" value={filters.has_anomaly} yes="With anomalies" no="Without anomalies" onChange={(value) => update({ has_anomaly: value })} />
        <TriState label="Replays" value={filters.is_replay} yes="Replays only" no="Originals only" onChange={(value) => update({ is_replay: value })} />
      </div>
    </div>
  );
}

export function ExecutionsView() {
  const [params, setParams] = useUrlState();
  const filters = parseFilters(params);
  const now = useNow();
  // A rolling range moves with the clock; rounding to the minute keeps the request (and its cache key) stable.
  const minute = Math.floor((now ?? 0) / 60_000) * 60_000;
  const { data, error, refetch, isPlaceholderData, isFetching } = useExecutions(toListParams(filters, minute), {
    enabled: filters.range === null || now !== null,
    refetchInterval: LIST_POLL_MS,
  });
  const active = activeFilterCount(filters);

  return (
    <Page
      title="Executions"
      description="Every run of every agent. Filters, sorting and paging are applied by the API."
      actions={
        <>
          <Refreshing active={isFetching && data !== undefined} />
          {data && <span className="num text-fg-muted">{pluralize(data.total, "execution")}</span>}
        </>
      }
    >
      <div className="overflow-hidden rounded-lg border border-line-subtle bg-surface">
        <Filters filters={filters} set={(patch) => setParams(patch)} />
        {error ? (
          <ErrorState error={error} onRetry={() => void refetch()} title="Executions could not be loaded" compact />
        ) : (
          <>
            <ExecutionsTable
              rows={data?.items}
              sort={filters.sort}
              onSortChange={(sort) => setParams({ sort: sort === "-started_at" ? null : sort, offset: null })}
              stale={isPlaceholderData}
              skeletonRows={12}
              empty={
                <div className="p-6">
                  {active > 0 ? (
                    <EmptyState
                      icon={SearchX}
                      title="No executions match these filters"
                      description={`${pluralize(active, "filter is", "filters are")} narrowing the list. Loosen or clear them to see more.`}
                      action={
                        <Button variant="outline" size="sm" onClick={() => setParams(CLEARED)}>
                          Clear filters
                        </Button>
                      }
                    />
                  ) : (
                    <EmptyState
                      icon={Inbox}
                      title="No executions yet"
                      description="Runs appear here as soon as an agent instrumented with the Ghostwatch SDK reports one. To create sample history:"
                      command="cd demo && uv run python seed.py"
                    />
                  )}
                </div>
              }
            />
            {data && (
              <Pagination
                total={data.total}
                limit={data.limit}
                offset={data.offset}
                onOffsetChange={(offset) => setParams({ offset: offset === 0 ? null : String(offset) }, "push")}
                noun="executions"
              />
            )}
          </>
        )}
      </div>
    </Page>
  );
}
