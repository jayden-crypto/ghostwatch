import type { Metadata } from "next";

import { NotImplemented } from "@/components/data/empty-state";
import { Page } from "@/components/shell/page";

export const metadata: Metadata = { title: "Anomalies" };

export default function AnomaliesPage() {
  return (
    <Page title="Anomalies" description="Runs that broke a deterministic rule, with the evidence.">
      <NotImplemented what="The anomaly feed" issue="F8, #26" />
    </Page>
  );
}
