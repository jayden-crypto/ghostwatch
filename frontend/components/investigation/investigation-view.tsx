"use client";

/** /investigations/[executionId]: the investigation of one execution, with the run it is about. */
import { ListTree } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { StatusBadge } from "@/components/data/badges";
import { Duration, IdChip } from "@/components/data/values";
import { Page } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isNotFound } from "@/lib/api/errors";
import { useTrace } from "@/lib/api/hooks";
import type { ID } from "@/lib/api/types";

import { InvestigationPanel } from "./investigation-panel";

/**
 * The page's body. The id comes from the URL on the client, so the server never streams this page's body. React reveals streamed
 * content on an animation frame, and a window that is not on screen draws none: the page would stay empty and
 * never fetch until shown.
 */
export function InvestigationRoute() {
  const { executionId } = useParams<{ executionId: string }>();
  return <InvestigationView executionId={executionId} />;
}

export function InvestigationView({ executionId }: { executionId: ID }) {
  // The trace names the run and its steps; the report only carries ids.
  const trace = useTrace(executionId);
  const execution = trace.data?.execution;
  return (
    <Page
      title="Investigation"
      description={
        execution ? (
          <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <Link href={`/agents/${execution.agent_id}`} className="rounded-sm text-fg underline-offset-2 hover:underline">
              {execution.agent_name}
            </Link>
            <StatusBadge status={execution.status} />
            <IdChip id={execution.id} href={`/executions/${execution.id}`} />
            <Duration ms={execution.duration_ms} />
            {execution.error && (
              <code className="font-mono text-xs">
                <span className="text-failed">{execution.error.type}</span>: {execution.error.message}
              </code>
            )}
          </span>
        ) : trace.error ? (
          <span>
            {isNotFound(trace.error) ? "This execution does not exist." : "The execution could not be loaded."} <IdChip id={executionId} />
          </span>
        ) : (
          <Skeleton className="h-4 w-96" />
        )
      }
      actions={
        <Button asChild variant="outline" size="sm">
          <Link href={`/executions/${executionId}`}>
            <ListTree aria-hidden="true" />
            Open trace
          </Link>
        </Button>
      }
    >
      <InvestigationPanel executionId={executionId} steps={trace.data?.steps} />
    </Page>
  );
}
