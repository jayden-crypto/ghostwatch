import type { Metadata } from "next";
import { Suspense } from "react";

import { AgentsView } from "@/components/agents/agents-view";

export const metadata: Metadata = { title: "Agents" };

export default function AgentsPage() {
  // The filters live in the query string, which is only known per request.
  return (
    <Suspense>
      <AgentsView />
    </Suspense>
  );
}
