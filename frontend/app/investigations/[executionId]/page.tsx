import type { Metadata } from "next";
import { Suspense } from "react";

import { InvestigationView } from "@/components/investigation/investigation-view";

export const metadata: Metadata = { title: "Investigation" };

export default function InvestigationPage({ params }: PageProps<"/investigations/[executionId]">) {
  return <Suspense>{params.then(({ executionId }) => <InvestigationView executionId={executionId} />)}</Suspense>;
}
