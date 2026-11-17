import type { Metadata } from "next";
import { Suspense } from "react";

import { InvestigationsView } from "@/components/investigation/investigations-view";

export const metadata: Metadata = { title: "Investigations" };

export default function InvestigationsPage() {
  // The filters live in the query string, which is only known per request.
  return (
    <Suspense>
      <InvestigationsView />
    </Suspense>
  );
}
