import type { Metadata } from "next";
import { Suspense } from "react";

import { TraceSkeleton, TraceView } from "@/components/trace/trace-view";

export const metadata: Metadata = { title: "Trace" };

export default function ExecutionPage({ params }: PageProps<"/executions/[id]">) {
  // The id and the query string are only known per request, so everything below streams in.
  return <Suspense fallback={<TraceSkeleton />}>{params.then(({ id }) => <TraceView executionId={id} />)}</Suspense>;
}
