import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createMockApi, type MockState } from "@/lib/api/mock";
import { fixtures } from "@/mocks/fixtures";

let state: MockState = null;
const mock = createMockApi({ latency: () => 0, state: () => state });
vi.mock("@/lib/api/client", () => ({ api: mock }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(window.location.search),
  useRouter: () => ({ push: vi.fn() }),
}));

const { OverviewView } = await import("@/components/overview/overview-view");
const { bucketLabel } = await import("@/components/overview/trend-chart");

const renderOverview = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <OverviewView />
    </QueryClientProvider>,
  );

/** One stat tile, looked up inside the totals section (the chart legend repeats some of the labels). */
const tile = (label: string) => within(within(screen.getByRole("region", { name: /^Totals/ })).getByText(label).parentElement!);

describe("Overview", () => {
  it("shows the totals exactly as /stats/overview reports them", async () => {
    state = null;
    const stats = fixtures["stats.overview.7d"];
    renderOverview();
    expect(await screen.findByText("Success rate")).toBeInTheDocument();
    expect(tile("Agents").getByText(String(stats.total_agents))).toBeInTheDocument();
    expect(tile("Executions").getByText(String(stats.total_executions))).toBeInTheDocument();
    expect(tile("Completed").getByText(String(stats.completed))).toBeInTheDocument();
    expect(tile("Failed").getByText(String(stats.failed))).toBeInTheDocument();
    expect(tile("Timed out").getByText(String(stats.timed_out))).toBeInTheDocument();
    expect(tile("Open anomalies").getByText(String(stats.open_anomalies))).toBeInTheDocument();
    expect(tile("Executions").getByText(`${stats.running} running now`)).toBeInTheDocument();
  });

  it("lists agents that need attention first, and the open anomalies", async () => {
    state = null;
    renderOverview();
    const health = within((await screen.findByRole("heading", { name: "Agent health" })).closest("section")!);
    await health.findByRole("link", { name: "Invoice Processor" });
    const names = health.getAllByRole("link").map((link) => link.textContent);
    const rank = { failing: 0, degraded: 1, healthy: 2, idle: 3 };
    const expected = [...fixtures["agents.list"].items]
      .sort((a, b) => rank[a.stats.health] - rank[b.stats.health] || a.name.localeCompare(b.name))
      .map((agent) => agent.name);
    expect(names.slice(1)).toEqual(expected);
    // The fixture world has at least one agent in every state, so the order is really exercised.
    expect(new Set(fixtures["agents.list"].items.map((agent) => agent.stats.health)).size).toBe(4);
    expect(health.getByText("never run")).toBeInTheDocument();

    const anomalies = within(screen.getByRole("heading", { name: "Open anomalies" }).closest("section")!);
    const ghost = await anomalies.findByRole("link", { name: "Reported completed, but submit_invoice never completed" });
    expect(ghost.getAttribute("href")).toMatch(/^\/executions\/exe_[0-9a-f]{32}\?anomaly=anm_[0-9a-f]{32}$/);
  });

  it("shows unknown rate and duration as dashes when nothing has run, never as zero", async () => {
    state = "empty";
    renderOverview();
    expect(await screen.findByText("No agents registered")).toBeInTheDocument();
    expect(tile("Success rate").getByText("—")).toBeInTheDocument();
    expect(tile("Avg duration").getByText("—")).toBeInTheDocument();
    expect(tile("Executions").getByText("0")).toBeInTheDocument();
    expect(screen.getByText("No executions yet")).toBeInTheDocument();
    expect(screen.getByText("No open anomalies")).toBeInTheDocument();
  });

  it("fails panel by panel, each with the API's message and a retry", async () => {
    state = "error";
    renderOverview();
    const alerts = await screen.findAllByRole("alert");
    expect(alerts).toHaveLength(5);
    for (const alert of alerts) {
      expect(within(alert).getByText("An internal error occurred.")).toBeInTheDocument();
      expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    }
  });
});

describe("bucketLabel", () => {
  it("labels buckets in UTC", () => {
    expect(bucketLabel("2026-11-14T17:00:00.000Z", "hour")).toBe("17:00");
    expect(bucketLabel("2026-11-14T00:00:00.000Z", "day")).toBe("Nov 14");
    expect(bucketLabel("2026-01-01T00:00:00.000Z", "day")).toBe("Jan 1");
  });
});
