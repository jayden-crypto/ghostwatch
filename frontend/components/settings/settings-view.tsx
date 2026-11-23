"use client";

/**
 * /settings: where the data on screen comes from, and what the backend says about itself.
 *
 * Nothing here can be edited. The data source is fixed when the app is built (environment
 * variables), and the rest is `GET /health` (contract §11) shown as it was answered. The page
 * receives the mode and base URL as props: only the route and lib/api/client.ts read the config.
 */
import { RotateCw } from "lucide-react";
import type { ReactNode } from "react";

import { ProviderBadge } from "@/components/data/badges";
import { ErrorState, Panel } from "@/components/data/states";
import { Timestamp } from "@/components/data/values";
import { Page } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ApiMode } from "@/lib/api/config";
import { LIST_POLL_MS, useHealth } from "@/lib/api/hooks";
import type { Health } from "@/lib/api/types";
import { cn } from "@/lib/utils";

function Field({ label, children, note }: { label: string; children: ReactNode; note?: ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_minmax(0,1fr)] gap-x-4 border-b border-line-subtle py-2.5 last:border-0">
      <dt className="text-xs leading-5 text-fg-muted">{label}</dt>
      <dd className="min-w-0">
        <div className="flex min-h-5 flex-wrap items-center gap-x-2">{children}</div>
        {note && <p className="mt-0.5 text-xs text-fg-subtle">{note}</p>}
      </dd>
    </div>
  );
}

const Code = ({ children }: { children: ReactNode }) => <code className="break-all font-mono text-xs">{children}</code>;

function Snippet({ label, children }: { label: string; children: string }) {
  return (
    <pre aria-label={label} className="mt-2 overflow-x-auto rounded-md border border-line-subtle bg-background px-3 py-2 font-mono text-xs leading-5 text-fg-muted">
      {children}
    </pre>
  );
}

/** A state word with a dot: green for ok, red for a problem, amber for something to look at. */
function State({ tone, children }: { tone: "ok" | "problem" | "attention"; children: ReactNode }) {
  const color = tone === "ok" ? "bg-completed" : tone === "problem" ? "bg-failed" : "bg-timed-out";
  const text = tone === "ok" ? undefined : tone === "problem" ? "text-failed" : "text-timed-out";
  return (
    <span className={cn("inline-flex items-center gap-2 text-sm font-medium", text)}>
      <span aria-hidden="true" className={cn("size-1.5 rounded-full", color)} />
      {children}
    </span>
  );
}

function DataSource({ mode, baseUrl }: { mode: ApiMode; baseUrl: string }) {
  return (
    <Panel title="Data source">
      <dl>
        <Field
          label="Mode"
          note={
            mode === "mock"
              ? "Everything in this dashboard comes from the contract fixtures in contract/fixtures, served by an in-memory adapter in the browser. No request is sent to a backend."
              : "Everything in this dashboard is read from the API below."
          }
        >
          {mode === "mock" ? <State tone="attention">Mock</State> : <State tone="ok">Live</State>}
        </Field>
        <Field label="API base URL" note={mode === "mock" ? "Configured, but not used in mock mode." : undefined}>
          <Code>{baseUrl}</Code>
        </Field>
      </dl>
      <p className="mt-3 text-xs text-fg-muted">
        Both are fixed when the app is built, so they cannot be changed from this page. Set them in <Code>frontend/.env.local</Code>, then run{" "}
        <Code>npm run build</Code> and <Code>npm run start</Code> again: restarting alone keeps the old values. The dev server (<Code>npm run dev</Code>) reads
        them when it starts. Any mode other than <Code>live</Code> means mock.
      </p>
      <Snippet label="Environment variables for the data source">{`NEXT_PUBLIC_API_MODE=${mode}\nNEXT_PUBLIC_API_BASE_URL=${baseUrl}`}</Snippet>
    </Panel>
  );
}

function providerNote(health: Health): ReactNode {
  if (health.llm_provider === "rule_based") return "Hypotheses come from deterministic rules written in code. No model is called; it needs no key and no network.";
  if (!health.llm_configured) return "The backend reports that this provider cannot run: no API key is set. Every investigation states which provider actually produced it.";
  return "Hypotheses are proposed by this model and must cite recorded facts. Only a deterministic signature can mark a root cause confirmed; the model never does.";
}

function Loading() {
  return (
    <div className="flex flex-col gap-3 py-1" aria-busy="true" aria-label="Loading backend status">
      <Skeleton className="h-4 w-56" />
      <Skeleton className="h-4 w-40" />
      <Skeleton className="h-4 w-48" />
    </div>
  );
}

export function SettingsView({ mode, baseUrl }: { mode: ApiMode; baseUrl: string }) {
  const { data: health, error, refetch, isFetching, dataUpdatedAt } = useHealth({ refetchInterval: LIST_POLL_MS });
  const fixtureNote = mode === "mock" && health !== undefined && !error && (
    <p className="mb-2 rounded-md border border-timed-out/40 px-3 py-2 text-xs text-fg-muted">
      <span className="font-medium text-timed-out">Mock mode.</span> These values are the <Code>health.get</Code> fixture, not the answer of a running backend.
    </p>
  );
  const failed = error ? (
    <ErrorState
      error={error}
      onRetry={() => void refetch()}
      title="The backend did not answer the health check"
      compact
    />
  ) : null;

  return (
    <Page title="Settings" description="Where the data comes from and what the backend reports about itself. Read-only.">
      <div className="grid max-w-5xl gap-4">
        <DataSource mode={mode} baseUrl={baseUrl} />

        <Panel
          title="Backend"
          action={
            <>
              {health && (
                <span className="text-xs text-fg-subtle">
                  checked <Timestamp value={new Date(dataUpdatedAt).toISOString()} />
                </span>
              )}
              <Button variant="ghost" size="sm" disabled={isFetching} onClick={() => void refetch()}>
                <RotateCw aria-hidden="true" className={isFetching ? "animate-spin [animation-duration:1.4s]" : undefined} />
                Check again
              </Button>
            </>
          }
        >
          {fixtureNote}
          {failed ? (
            <>
              {failed}
              {mode === "live" && (
                <>
                  <p className="mt-1 text-center text-xs text-fg-muted">
                    Asked <Code>{baseUrl}/health</Code>. To start the backend, from the repository root:
                  </p>
                  <Snippet label="Commands that start the backend">{"docker compose up -d\ncd backend && uv run alembic upgrade head && uv run uvicorn app.main:app"}</Snippet>
                </>
              )}
            </>
          ) : !health ? (
            <Loading />
          ) : (
            <dl>
              <Field label="API" note="GET /health answered. It answers whenever the backend process is up.">
                <State tone="ok">Reachable</State>
              </Field>
              <Field label="Version">
                <Code>{health.version}</Code>
              </Field>
              <Field
                label="Database"
                note={health.database === "ok" ? "The backend's test query to Postgres succeeded." : "The API is up, but its test query to Postgres failed. Lists and traces will not load until it is back."}
              >
                {health.database === "ok" ? <State tone="ok">OK</State> : <State tone="problem">Error</State>}
              </Field>
            </dl>
          )}
        </Panel>

        <Panel title="Investigations">
          {fixtureNote}
          {failed ? (
            <p className="py-2 text-fg-muted">Not known: the provider is reported by the health check, which did not answer.</p>
          ) : !health ? (
            <Loading />
          ) : (
            <>
              <dl>
                <Field label="Hypotheses by" note={providerNote(health)}>
                  <ProviderBadge provider={health.llm_provider} model={health.llm_model} className="text-sm text-fg" />
                </Field>
                <Field label="Can run">{health.llm_configured ? <State tone="ok">Yes</State> : <State tone="attention">No: not configured</State>}</Field>
                <Field label="Model">{health.llm_model ? <Code>{health.llm_model}</Code> : <span className="text-fg-subtle">None</span>}</Field>
              </dl>
              <p className="mt-3 text-xs text-fg-muted">
                Facts and confirmed root causes are always computed by backend code, whichever provider is set. The provider is chosen in the backend&apos;s{" "}
                <Code>.env</Code> at the repository root; restart the backend after changing it.
              </p>
              <Snippet label="Environment variables for the investigation provider">{"LLM_PROVIDER=rule_based   # or: fable\nANTHROPIC_API_KEY=          # needed for fable only\nLLM_MODEL=claude-fable-5-2"}</Snippet>
            </>
          )}
        </Panel>

        <Panel title="Access">
          <p className="text-fg-muted">
            The endpoints this dashboard reads are unauthenticated and meant for localhost only. Ingestion endpoints, used by the SDK, require the key in{" "}
            <Code>GHOSTWATCH_API_KEY</Code>. This is a known limitation of the MVP.
          </p>
        </Panel>
      </div>
    </Page>
  );
}
