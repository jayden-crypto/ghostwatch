import type { Metadata } from "next";

import { SettingsView } from "@/components/settings/settings-view";
import { API_BASE_URL, API_MODE } from "@/lib/api/config";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return <SettingsView mode={API_MODE} baseUrl={API_BASE_URL} />;
}
