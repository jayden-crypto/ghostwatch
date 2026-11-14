import type { Metadata } from "next";

import { NotImplemented } from "@/components/data/empty-state";
import { Page } from "@/components/shell/page";

export const metadata: Metadata = { title: "Replays" };

export default function ReplaysPage() {
  return (
    <Page title="Replays" description="Re-runs of recorded executions, compared with the original.">
      <NotImplemented what="The replay list" issue="F10, #30" />
    </Page>
  );
}
