import type { Metadata } from "next";
import { Suspense } from "react";

import { AgentView } from "@/components/agents/agent-view";

export const metadata: Metadata = { title: "Agent" };

export default function AgentPage({ params }: PageProps<"/agents/[id]">) {
  return <Suspense>{params.then(({ id }) => <AgentView agentId={id} />)}</Suspense>;
}
