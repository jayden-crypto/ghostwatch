import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { Step, Trace } from "@/lib/api/types";
import { fixtures } from "@/mocks/fixtures";

const schemaChange = fixtures["executions.trace.exe_0000000000000000000000000000000a"];
const tokenSpike = fixtures["executions.trace.exe_00000000000000000000000000000007"];
const rateLimit = fixtures["executions.trace.exe_00000000000000000000000000000048"];
const ghost = fixtures["executions.trace.exe_00000000000000000000000000000028"];

const traces = new Map<string, Trace>();
vi.mock("@/lib/api/client", () => ({
  api: {
    getTrace: async (id: string) => {
      const trace = traces.get(id);
      if (!trace) throw new Error(`no trace ${id}`);
      return trace;
    },
  },
}));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

// Imported after the mocks above so the components pick them up.
const { AnomalyStrip } = await import("@/components/trace/anomaly-strip");
const { StepInspector } = await import("@/components/trace/step-inspector");
const { TraceView } = await import("@/components/trace/trace-view");

const wrap = (ui: ReactElement) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TooltipProvider>{ui}</TooltipProvider>
    </QueryClientProvider>,
  );

const inspector = (step: Step, tab: "overview" | "input" | "output" | "error" | "metadata", attempts = 1) =>
  render(<StepInspector step={step} attempts={attempts} tab={tab} onTabChange={() => undefined} onClose={() => undefined} onSelectStep={() => undefined} />);

describe("StepInspector", () => {
  it("shows every scalar field of a step on Overview", () => {
    const step = rateLimit.steps[2]; // retrieve_kb, attempt 2 of 3, failed
    inspector(step, "overview", 3);
    const panel = within(screen.getByRole("tabpanel"));
    expect(panel.getByText("Failed")).toBeInTheDocument();
    expect(panel.getByText("Tool call")).toBeInTheDocument();
    expect(panel.getByText(`#${step.ordinal}`, { exact: false })).toBeInTheDocument();
    expect(panel.getByText("of 3", { exact: false })).toBeInTheDocument();
    expect(panel.getByText("retrieve_kb")).toBeInTheDocument(); // tool_name
    expect(panel.getByText(step.id)).toBeInTheDocument();
    expect(panel.getByText("None (top level)")).toBeInTheDocument();
    // Tokens and model were not reported for a tool call: dashes, not zeros.
    expect(panel.getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });

  it("says a running step has not ended instead of inventing an end", () => {
    const running = { ...rateLimit.steps[0], status: "running" as const, ended_at: null, duration_ms: null };
    inspector(running, "overview");
    expect(screen.getByText("Not ended")).toBeInTheDocument();
    expect(screen.getByText("Still running")).toBeInTheDocument();
  });

  it("shows the error type, message and stack trace", () => {
    const failed = schemaChange.steps[2];
    inspector(failed, "error");
    expect(screen.getByText("KeyError")).toBeInTheDocument();
    expect(screen.getByText("'results'")).toBeInTheDocument();
    expect(screen.getByText(/Traceback \(most recent call last\)/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy stack trace" })).toBeInTheDocument();
  });

  it("says so when a step recorded no error", () => {
    inspector(schemaChange.steps[0], "error");
    expect(screen.getByText("This step recorded no error.")).toBeInTheDocument();
  });

  it("announces a truncated output", () => {
    inspector(tokenSpike.steps[1], "output");
    expect(screen.getByRole("note")).toHaveTextContent(/Payload truncated — \d+ KB/);
  });

  it("shows input and metadata as recorded", () => {
    const step = schemaChange.steps[1];
    const { unmount } = inspector(step, "input");
    expect(screen.getByText('"how do teams trace what an ai agent did"')).toBeInTheDocument();
    unmount();
    inspector(step, "metadata");
    expect(screen.getByText('"side_effects"')).toBeInTheDocument();
  });

  it("reports tab changes and close", async () => {
    const user = userEvent.setup();
    const onTabChange = vi.fn();
    const onClose = vi.fn();
    render(<StepInspector step={schemaChange.steps[2]} attempts={1} tab="overview" onTabChange={onTabChange} onClose={onClose} onSelectStep={() => undefined} />);
    await user.click(screen.getByRole("tab", { name: "Error" }));
    expect(onTabChange).toHaveBeenCalledWith("error");
    await user.click(screen.getByRole("button", { name: "Close step inspector" }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe("AnomalyStrip", () => {
  it("renders nothing when the execution has no anomalies", () => {
    const { container } = render(<AnomalyStrip anomalies={[]} activeId={null} onActiveChange={() => undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the rule's explanation and evidence when opened, most severe first", async () => {
    const user = userEvent.setup();
    const onActiveChange = vi.fn();
    const anomalies = tokenSpike.anomalies;
    const { rerender } = render(<AnomalyStrip anomalies={anomalies} activeId={null} onActiveChange={onActiveChange} />);
    expect(screen.queryByText(/Rule fires above/)).not.toBeInTheDocument();
    const [first] = screen.getAllByRole("button");
    await user.click(first);
    expect(onActiveChange).toHaveBeenCalledWith(anomalies[0].id);
    rerender(<AnomalyStrip anomalies={anomalies} activeId={anomalies[0].id} onActiveChange={onActiveChange} />);
    expect(screen.getByText(anomalies[0].explanation)).toBeInTheDocument();
    expect(screen.getByText(anomalies[0].evidence[0].label)).toBeInTheDocument();
  });

  it("links evidence that points at an event to that event in the raw log", () => {
    const [anomaly] = ghost.anomalies;
    render(<AnomalyStrip anomalies={ghost.anomalies} activeId={anomaly.id} onActiveChange={() => undefined} />);
    const event = anomaly.evidence.find((item) => item.kind === "event")!;
    expect(screen.getByRole("link", { name: "Open event" })).toHaveAttribute(
      "href",
      `/executions/${anomaly.execution_id}?tab=events&event=${event.ref_id}`,
    );
    // Evidence about this same execution does not link to the page we are already on.
    expect(screen.queryByRole("link", { name: "Open execution" })).not.toBeInTheDocument();
  });
});

describe("TraceView", () => {
  it("shows an execution with no steps as evidence, not as an empty page", async () => {
    const empty: Trace = {
      ...ghost,
      execution: { ...ghost.execution, id: "exe_empty", step_count: 0 },
      steps: [],
      anomalies: [],
    };
    traces.set("exe_empty", empty);
    wrap(<TraceView executionId="exe_empty" />);
    expect(await screen.findByText("No steps were recorded for this execution")).toBeInTheDocument();
    expect(screen.getByText(/ended with status completed without recording a single step/)).toBeInTheDocument();
  });

  it("shows the header from API fields, with unknown values as dashes", async () => {
    traces.set(schemaChange.execution.id, schemaChange);
    wrap(<TraceView executionId={schemaChange.execution.id} />);
    expect(await screen.findByRole("heading", { name: "Research Assistant" })).toBeInTheDocument();
    expect(screen.getByText("361 ms")).toBeInTheDocument();
    expect(screen.getByText("Replayed 2×")).toBeInTheDocument();
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("KeyError: 'results'");
    // tokens_total and cost_usd are null on this run.
    const tokens = screen.getByText("Tokens").parentElement!;
    expect(within(tokens).getByText("—")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Investigation/ })).toHaveAttribute("href", `/investigations/${schemaChange.execution.id}`);
  });
});
