import type { Metadata } from "next";
import { Suspense } from "react";

import { ReplayView } from "@/components/replay/replay-view";

export const metadata: Metadata = { title: "Replay" };

export default function ReplayPage({ params }: PageProps<"/replays/[id]">) {
  return <Suspense>{params.then(({ id }) => <ReplayView replayId={id} />)}</Suspense>;
}
