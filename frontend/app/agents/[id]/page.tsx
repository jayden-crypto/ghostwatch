import type { Metadata } from "next";
import { Suspense } from "react";

import { AgentRoute } from "@/components/agents/agent-view";

export const metadata: Metadata = { title: "Agent" };

export default function AgentPage() {
  // The query string is only known in the browser, so the view renders there (see AgentRoute).
  return (
    <Suspense>
      <AgentRoute />
    </Suspense>
  );
}
