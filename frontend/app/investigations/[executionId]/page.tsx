import type { Metadata } from "next";
import { Suspense } from "react";

import { InvestigationRoute } from "@/components/investigation/investigation-view";

export const metadata: Metadata = { title: "Investigation" };

export default function InvestigationPage() {
  // The id is read in the browser (see InvestigationRoute).
  return (
    <Suspense>
      <InvestigationRoute />
    </Suspense>
  );
}
