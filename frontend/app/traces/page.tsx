import type { Metadata } from "next";

import { NotImplemented } from "@/components/data/empty-state";
import { Page } from "@/components/shell/page";

export const metadata: Metadata = { title: "Traces" };

export default function TracesPage() {
  return (
    <Page title="Traces" description="Open the step-by-step trace of an execution.">
      <NotImplemented what="The trace finder" issue="F6, #22" />
    </Page>
  );
}
