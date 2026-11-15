import type { Metadata } from "next";
import { Suspense } from "react";

import { AnomaliesView } from "@/components/anomalies/anomalies-view";

export const metadata: Metadata = { title: "Anomalies" };

export default function AnomaliesPage() {
  // The filters live in the query string, which is only known per request.
  return (
    <Suspense>
      <AnomaliesView />
    </Suspense>
  );
}
