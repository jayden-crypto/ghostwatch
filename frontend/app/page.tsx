import { NotImplemented } from "@/components/data/empty-state";
import { Page } from "@/components/shell/page";

export default function OverviewPage() {
  return (
    <Page title="Overview" description="Agents, executions and anomalies at a glance.">
      <NotImplemented what="The overview" issue="F4, #23" />
    </Page>
  );
}
