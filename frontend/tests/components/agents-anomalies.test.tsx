import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { createMockApi, type MockState } from "@/lib/api/mock";
import { fixtures } from "@/mocks/fixtures";

let state: MockState = null;
let mock = createMockApi({ latency: () => 0, state: () => state });
// The components reach the API through this object, so each test can swap in a fresh mock.
const api = new Proxy({}, { get: (_target, method: string) => (mock as unknown as Record<string, unknown>)[method] });
vi.mock("@/lib/api/client", () => ({ api }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(window.location.search),
  useRouter: () => ({ push: vi.fn() }),
}));

const { AgentView } = await import("@/components/agents/agent-view");
const { AgentsView } = await import("@/components/agents/agents-view");
const { AnomaliesView } = await import("@/components/anomalies/anomalies-view");
const { AnomalyCard } = await import("@/components/anomalies/anomaly-card");

const wrap = (ui: ReactElement) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

const allAnomalies = fixtures["anomalies.list"].items;
const ghost = allAnomalies.find((anomaly) => anomaly.type === "ghost_completion")!;
const agents = fixtures["agents.list"].items;

beforeEach(() => {
  state = null;
  mock = createMockApi({ latency: () => 0, state: () => state });
  window.history.replaceState(null, "", "/");
});

describe("AnomalyCard", () => {
  it("shows the rule's explanation verbatim, the rule id and a link to the execution", () => {
    wrap(<AnomalyCard anomaly={ghost} />);
    expect(screen.getByText(ghost.explanation)).toBeInTheDocument();
    expect(screen.getByText("ghost_completion.v1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open execution" })).toHaveAttribute("href", `/executions/${ghost.execution_id}?anomaly=${ghost.id}`);
  });

  it("keeps evidence behind a toggle and links step and event evidence to the trace", async () => {
    const user = userEvent.setup();
    const retries = allAnomalies.find((anomaly) => anomaly.type === "excessive_retries")!;
    wrap(<AnomalyCard anomaly={retries} />);
    expect(screen.queryByRole("link", { name: "Open step" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Evidence · 2 items/ }));
    const links = screen.getAllByRole("link", { name: "Open step" });
    expect(links).toHaveLength(2);
    expect(links[0].getAttribute("href")).toBe(`/executions/${retries.execution_id}?step=${retries.evidence[0].ref_id}`);
  });

  it.each([
    ["open", ["Acknowledge", "Resolve"]],
    ["acknowledged", ["Resolve", "Reopen"]],
    ["resolved", ["Reopen"]],
  ] as const)("offers the right actions for a %s anomaly", (status, labels) => {
    wrap(<AnomalyCard anomaly={{ ...ghost, status }} />);
    const actions = screen.getAllByRole("button").map((button) => button.textContent).filter((text) => !text?.startsWith("Evidence"));
    expect(actions).toEqual(labels);
  });

  it("changes the status through the API and says so when the API refuses", async () => {
    const user = userEvent.setup();
    wrap(<AnomalyCard anomaly={ghost} />);
    await user.click(screen.getByRole("button", { name: "Acknowledge" }));
    await waitFor(async () => expect((await mock.getAnomaly(ghost.id)).status).toBe("acknowledged"));

    mock = { ...mock, updateAnomaly: async () => Promise.reject(new ApiError("not_found", "PATCH /anomalies is not available.", 404)) };
    await user.click(screen.getByRole("button", { name: "Resolve" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The status could not be changed: PATCH /anomalies is not available.");
  });
});

describe("Anomalies page", () => {
  it("shows open anomalies by default, grouped most severe first", async () => {
    wrap(<AnomaliesView />);
    const groups = await screen.findAllByRole("region", { name: /^(Critical|High|Medium|Low)/ });
    expect(groups.map((group) => within(group).getAllByRole("heading", { level: 2 })[0].textContent?.replace(/\d+$/, ""))).toEqual(["Critical", "High", "Medium"]);
    const shown = screen.getAllByRole("article");
    expect(shown).toHaveLength(allAnomalies.filter((anomaly) => anomaly.status === "open").length);
    // The critical anomaly's evidence is open without a click.
    expect(within(groups[0]).getByRole("button", { name: /Evidence/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("pins a linked anomaly even when the filters would hide it", async () => {
    const resolved = allAnomalies.find((anomaly) => anomaly.status === "resolved")!;
    window.history.replaceState(null, "", `/anomalies?anomaly=${resolved.id}&severity=critical`);
    wrap(<AnomaliesView />);
    const pinned = within(await screen.findByRole("region", { name: "Linked anomaly" }));
    expect(await pinned.findByRole("heading", { name: resolved.title })).toBeInTheDocument();
    expect(pinned.getByText("Resolved")).toBeInTheDocument();
  });

  it("says there are no open anomalies when there are none", async () => {
    state = "empty";
    wrap(<AnomaliesView />);
    expect(await screen.findByText("No open anomalies")).toBeInTheDocument();
  });
});

describe("Agents", () => {
  it("lists every agent with the health and success rate the API reports", async () => {
    wrap(<AgentsView />);
    for (const agent of agents) {
      const row = (await screen.findByRole("link", { name: `Open agent ${agent.name}` })).closest("tr")!;
      expect(within(row).getByText(agent.slug)).toBeInTheDocument();
      expect(row).toHaveTextContent(agent.stats.health === "idle" ? "Never run" : /ago|just now|UTC/);
    }
    const idle = screen.getByRole("link", { name: "Open agent PR Reviewer" }).closest("tr")!;
    expect(within(idle).getByText("Idle")).toBeInTheDocument();
    // Success rate and average duration are unknown for an agent that never ran: dashes, not 0% and 0 ms.
    expect(within(idle).getAllByText("—")).toHaveLength(2);
    expect(within(idle).queryByText("0%")).not.toBeInTheDocument();
  });

  it("shows one agent's own numbers, runs and anomalies", async () => {
    const digest = agents.find((agent) => agent.slug === "ticket-digest")!;
    wrap(<AgentView agentId={digest.id} />);
    expect(await screen.findByRole("heading", { level: 1, name: /Ticket Digest/ })).toBeInTheDocument();
    const totals = within(screen.getByRole("region", { name: "Totals for this agent" }));
    expect(within(totals.getByText("Executions").parentElement!).getByText(String(digest.stats.total_executions))).toBeInTheDocument();
    expect(within(totals.getByText("Timed out").parentElement!).getByText(String(digest.stats.timed_out))).toBeInTheDocument();
    const own = allAnomalies.filter((anomaly) => anomaly.agent_id === digest.id);
    await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(own.length));
    // Open anomalies come before acknowledged and resolved ones.
    const statuses = screen.getAllByRole("article").map((card) => card.querySelector("[data-enum=AnomalyStatus]")!.textContent);
    expect(statuses).toEqual([...statuses].sort((a, b) => ["Open", "Acknowledged", "Resolved"].indexOf(a!) - ["Open", "Acknowledged", "Resolved"].indexOf(b!)));
  });

  it("says so when the agent does not exist", async () => {
    wrap(<AgentView agentId="agt_ffffffffffffffffffffffffffffffff" />);
    expect(await screen.findByText("This agent does not exist")).toBeInTheDocument();
  });
});
