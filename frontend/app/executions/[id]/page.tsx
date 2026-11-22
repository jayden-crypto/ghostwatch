import type { Metadata } from "next";
import { Suspense } from "react";

import { TraceRoute, TraceSkeleton } from "@/components/trace/trace-view";

export const metadata: Metadata = { title: "Trace" };

export default function ExecutionPage() {
  // The id is read in the browser (see TraceRoute).
  return (
    <Suspense fallback={<TraceSkeleton />}>
      <TraceRoute />
    </Suspense>
  );
}
