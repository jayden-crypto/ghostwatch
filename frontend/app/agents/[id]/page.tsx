import type { Metadata } from "next";
import { Suspense } from "react";

import { AgentRoute } from "@/components/agents/agent-view";

export const metadata: Metadata = { title: "Agent" };

export default function AgentPage() {
  // The id is read in the browser (see AgentRoute).
  return (
    <Suspense>
      <AgentRoute />
    </Suspense>
  );
}
