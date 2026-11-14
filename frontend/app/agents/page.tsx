import type { Metadata } from "next";

import { NotImplemented } from "@/components/data/empty-state";
import { Page } from "@/components/shell/page";

export const metadata: Metadata = { title: "Agents" };

export default function AgentsPage() {
  return (
    <Page title="Agents" description="Every registered agent, with its health and recent history.">
      <NotImplemented what="The agents list" issue="F7, #25" />
    </Page>
  );
}
