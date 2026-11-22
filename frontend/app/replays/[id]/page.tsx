import type { Metadata } from "next";
import { Suspense } from "react";

import { ReplayRoute } from "@/components/replay/replay-view";

export const metadata: Metadata = { title: "Replay" };

export default function ReplayPage() {
  // The id is read in the browser (see ReplayRoute).
  return (
    <Suspense>
      <ReplayRoute />
    </Suspense>
  );
}
