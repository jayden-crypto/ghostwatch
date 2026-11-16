import type { Metadata } from "next";
import { Suspense } from "react";

import { ReplaysView } from "@/components/replay/replays-view";

export const metadata: Metadata = { title: "Replays" };

export default function ReplaysPage() {
  // The filters live in the query string, which is only known per request.
  return (
    <Suspense>
      <ReplaysView />
    </Suspense>
  );
}
