import type { Metadata } from "next";

import { NotImplemented } from "@/components/data/empty-state";
import { Page } from "@/components/shell/page";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <Page title="Settings" description="Where the data comes from and whether the backend is healthy.">
      <NotImplemented what="The settings page" issue="F11, #31" />
    </Page>
  );
}
