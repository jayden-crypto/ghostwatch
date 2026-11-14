import type { Metadata } from "next";

import { NotImplemented } from "@/components/data/empty-state";
import { Page } from "@/components/shell/page";

export const metadata: Metadata = { title: "Executions" };

export default function ExecutionsPage() {
  return (
    <Page title="Executions" description="Every run of every agent.">
      <NotImplemented what="The executions table" issue="F5, #24" />
    </Page>
  );
}
