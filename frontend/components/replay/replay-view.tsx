"use client";

/**
 * /replays/[id]: one replay in whichever state it is in (contract §10 lifecycle).
 *
 * pending → a worker has to claim it · claimed → the worker is running the agent ·
 * completed → the comparison · failed → the replay could not be run.
 * Polls every 2 s until the status is terminal (lib/api/hooks.ts).
 */
import { ListTree, LoaderCircle, Clock } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ReplayModeBadge, ReplayStatusBadge } from "@/components/data/badges";
import { ErrorState } from "@/components/data/states";
import { IdChip, Timestamp } from "@/components/data/values";
import { Page } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isNotFound } from "@/lib/api/errors";
import { useReplay } from "@/lib/api/hooks";
import type { ID, Replay } from "@/lib/api/types";
import { formatDuration } from "@/lib/format";
import { LIVE_RULE, SANDBOX_RULE, WORKER_COMMAND } from "@/lib/replay";
import { useElapsed } from "@/lib/use-now";

import { ReplayComparisonView } from "./replay-comparison";

/** Status, mode, the two runs and the request time of a replay, on one line. */
function ReplayMeta({ replay }: { replay: Replay }) {
  return (
    <span className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs">
      <ReplayStatusBadge status={replay.status} />
      <ReplayModeBadge mode={replay.mode} />
      <span>
        of <IdChip id={replay.original_execution_id} href={`/executions/${replay.original_execution_id}`} />
      </span>
      <span>
        requested <Timestamp value={replay.requested_at} />
      </span>
      <IdChip id={replay.id} className="text-fg-subtle" />
    </span>
  );
}

function Waiting({ replay }: { replay: Replay }) {
  const pending = replay.status === "pending";
  const elapsed = useElapsed(pending ? replay.requested_at : (replay.claimed_at ?? replay.requested_at));
  const Icon = pending ? Clock : LoaderCircle;
  return (
    <div role="status" className="flex flex-col items-center gap-3 rounded-lg border border-line px-6 py-12 text-center">
      <Icon className={pending ? "size-5 text-fg-muted" : "size-5 animate-spin text-running [animation-duration:1.4s]"} aria-hidden="true" />
      <div className="max-w-xl">
        <p className="text-sm font-medium">{pending ? "Waiting for a replay worker" : "A worker is replaying the run"}</p>
        <p className="mt-1 text-fg-muted">
          {pending
            ? "Replays are run by a replay worker, a process that has the agent's code. This one stays pending until a worker claims it. If none is running, start one:"
            : "The worker is re-running the agent and reporting it as a new execution. The comparison appears here when that execution ends."}
        </p>
        {pending && (
          <code className="mt-3 inline-block rounded-md border border-line-subtle bg-surface px-2.5 py-1.5 font-mono text-xs text-fg-muted">{WORKER_COMMAND}</code>
        )}
        {!pending && replay.replay_execution_id && (
          <p className="mt-3">
            <Link href={`/executions/${replay.replay_execution_id}`} className="rounded-sm text-xs underline underline-offset-2 hover:text-fg">
              Watch the replay run
            </Link>
          </p>
        )}
        <p className="num mt-3 font-mono text-xs text-fg-subtle">
          {elapsed === null ? "…" : `${pending ? "pending" : "running"} for ${elapsed < 60_000 ? `${Math.floor(elapsed / 1000)} s` : formatDuration(elapsed)}`} · checking every 2 s
        </p>
        <p className="mt-3 text-xs text-fg-subtle">
          <span className="font-medium text-fg-muted">{replay.mode === "sandbox" ? "Sandbox." : "Live, side effects authorized."}</span>{" "}
          {replay.mode === "sandbox" ? SANDBOX_RULE : LIVE_RULE}
        </p>
      </div>
    </div>
  );
}

export function ReplayBody({ replay }: { replay: Replay }) {
  if (replay.status === "pending" || replay.status === "claimed") return <Waiting replay={replay} />;
  if (replay.status === "failed") {
    return (
      <div role="alert" className="flex flex-col gap-1 rounded-lg border border-failed/30 px-4 py-3">
        <p className="text-sm font-medium">The replay could not be run</p>
        <p className="text-fg-muted">
          {replay.error ? (
            <>
              <code className="font-mono text-xs text-failed">{replay.error.type}</code>: {replay.error.message}
            </>
          ) : (
            "No error was recorded."
          )}
        </p>
        <p className="text-xs text-fg-subtle">The worker reported that it could not start the replay. This says nothing about the agent: there is no replay run to compare.</p>
      </div>
    );
  }
  if (!replay.comparison) {
    // The contract says a completed replay always has a comparison; say so if one does not.
    return <ErrorState error={new Error("The replay is completed but the API returned no comparison.")} title="The comparison is missing" />;
  }
  return <ReplayComparisonView replay={replay} comparison={replay.comparison} />;
}

/**
 * The page's body, with the id read in the browser by `useParams()`. When the page read `params` on the server, its body
 * came in the server's stream, which React reveals only on an animation frame; a window that is not on screen draws
 * none, so the page stayed empty and fetched nothing until shown. Read this way, the body appears and fetches without
 * a frame (`e2e/no-frames.spec.ts`), although `next build` still lists the route as partial prerender.
 */
export function ReplayRoute() {
  const { id } = useParams<{ id: string }>();
  return <ReplayView replayId={id} />;
}

export function ReplayView({ replayId }: { replayId: ID }) {
  const { data: replay, error, refetch } = useReplay(replayId);
  return (
    <Page
      title="Replay"
      description={
        replay ? (
          <span className="flex flex-col gap-1.5">
            <ReplayMeta replay={replay} />
            {replay.note && <span className="max-w-3xl text-fg">“{replay.note}”</span>}
          </span>
        ) : error ? (
          <span>
            {isNotFound(error) ? "This replay does not exist." : "The replay could not be loaded."} <IdChip id={replayId} />
          </span>
        ) : (
          <Skeleton className="h-4 w-96" />
        )
      }
      actions={
        replay && (
          <>
            <Button asChild variant="outline" size="sm">
              <Link href={`/executions/${replay.original_execution_id}`}>
                <ListTree aria-hidden="true" />
                Original trace
              </Link>
            </Button>
            {replay.replay_execution_id && (
              <Button asChild variant="outline" size="sm">
                <Link href={`/executions/${replay.replay_execution_id}`}>
                  <ListTree aria-hidden="true" />
                  Replay trace
                </Link>
              </Button>
            )}
          </>
        )
      }
    >
      {error ? (
        <ErrorState error={error} onRetry={isNotFound(error) ? undefined : () => void refetch()} title={isNotFound(error) ? "Replay not found" : "The replay could not be loaded"} />
      ) : replay ? (
        <ReplayBody replay={replay} />
      ) : (
        <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading replay">
          <Skeleton className="h-24 w-full rounded-lg" />
          <Skeleton className="h-56 w-full rounded-lg" />
          <Skeleton className="h-40 w-full rounded-lg" />
        </div>
      )}
    </Page>
  );
}
