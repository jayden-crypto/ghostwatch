import { Suspense } from "react";

import { OverviewView } from "@/components/overview/overview-view";

export default function OverviewPage() {
  // The time window lives in the query string, which is only known per request.
  return (
    <Suspense>
      <OverviewView />
    </Suspense>
  );
}
