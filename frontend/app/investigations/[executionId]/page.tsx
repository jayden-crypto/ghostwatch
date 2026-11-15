import type { Metadata } from "next";

import { NotImplemented } from "@/components/data/empty-state";
import { Page } from "@/components/shell/page";

export const metadata: Metadata = { title: "Investigation" };

export default function InvestigationPage() {
  return (
    <Page title="Investigation" description="Facts, hypotheses and recommendations for one execution.">
      <NotImplemented what="The investigation report" issue="F9, #27" />
    </Page>
  );
}
