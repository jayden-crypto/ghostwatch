import type { Metadata } from "next";
import { Suspense } from "react";

import { ExecutionsView } from "@/components/executions/executions-view";

export const metadata: Metadata = { title: "Executions" };

export default function ExecutionsPage() {
  // The filters live in the query string, which is only known per request.
  return (
    <Suspense>
      <ExecutionsView />
    </Suspense>
  );
}
