import type { Metadata } from "next";

import { NotImplemented } from "@/components/data/empty-state";
import { Page } from "@/components/shell/page";

export const metadata: Metadata = { title: "Investigations" };

export default function InvestigationsPage() {
  return (
    <Page title="Investigations" description="Facts, hypotheses and recommendations for failed or anomalous runs.">
      <NotImplemented what="The investigations list" issue="F9, #27" />
    </Page>
  );
}
