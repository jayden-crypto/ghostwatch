import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import type { Health } from "@/lib/api/types";
import { fixtures } from "@/mocks/fixtures";

const BASE_URL = "http://localhost:8000/api/v1";
let answer: Health | Error = fixtures["health.get"];
let calls = 0;
vi.mock("@/lib/api/client", () => ({
  api: {
    health: async () => {
      calls += 1;
      if (answer instanceof Error) throw answer;
      return answer;
    },
  },
}));

const { SettingsView } = await import("@/components/settings/settings-view");

const renderSettings = (mode: "mock" | "live") =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SettingsView mode={mode} baseUrl={BASE_URL} />
    </QueryClientProvider>,
  );

const panel = (title: string) => within(screen.getByRole("heading", { level: 2, name: title }).closest("section")!);
/** The value cell of a labelled field. */
const field = (scope: ReturnType<typeof within>, label: string) => within(scope.getByText(label, { selector: "dt" }).nextElementSibling as HTMLElement);

beforeEach(() => {
  answer = fixtures["health.get"];
  calls = 0;
});

describe("data source", () => {
  it("says mock data is fixtures, and that the API URL is not in use", () => {
    renderSettings("mock");
    const source = panel("Data source");
    expect(field(source, "Mode").getByText("Mock")).toBeInTheDocument();
    expect(field(source, "Mode").getByText(/contract fixtures/)).toBeInTheDocument();
    expect(field(source, "API base URL").getByText(BASE_URL)).toBeInTheDocument();
    expect(field(source, "API base URL").getByText("Configured, but not used in mock mode.")).toBeInTheDocument();
    expect(source.getByLabelText("Environment variables for the data source")).toHaveTextContent(`NEXT_PUBLIC_API_MODE=mock NEXT_PUBLIC_API_BASE_URL=${BASE_URL}`);
  });

  it("says live data is read from the API, with no fixture warning anywhere", async () => {
    renderSettings("live");
    const source = panel("Data source");
    expect(field(source, "Mode").getByText("Live")).toBeInTheDocument();
    expect(source.queryByText(/not used in mock mode/)).not.toBeInTheDocument();
    await panel("Backend").findByText("Reachable");
    expect(screen.queryByText("Mock mode.")).not.toBeInTheDocument();
  });

  it("offers nothing to edit", async () => {
    renderSettings("live");
    await panel("Backend").findByText("Reachable");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual(["Check again"]);
  });
});

describe("backend health", () => {
  it("shows /health as answered: version, database, provider", async () => {
    renderSettings("live");
    const backend = panel("Backend");
    expect(await backend.findByText("Reachable")).toBeInTheDocument();
    const health = fixtures["health.get"];
    expect(field(backend, "Version").getByText(health.version)).toBeInTheDocument();
    expect(field(backend, "Database").getByText("OK")).toBeInTheDocument();

    const investigations = panel("Investigations");
    expect(field(investigations, "Hypotheses by").getByText("Rule-based")).toBeInTheDocument();
    expect(field(investigations, "Hypotheses by").getByText(/No model is called/)).toBeInTheDocument();
    expect(field(investigations, "Can run").getByText("Yes")).toBeInTheDocument();
    expect(field(investigations, "Model").getByText("None")).toBeInTheDocument();
  });

  it("labels the health values as a fixture in mock mode", async () => {
    renderSettings("mock");
    await panel("Backend").findByText("Reachable");
    expect(panel("Backend").getByText("Mock mode.")).toBeInTheDocument();
    expect(panel("Investigations").getByText("Mock mode.")).toBeInTheDocument();
  });

  it("shows a database error as an error while the API is still reachable", async () => {
    answer = { ...fixtures["health.get"], database: "error" };
    renderSettings("live");
    const backend = panel("Backend");
    expect(await backend.findByText("Reachable")).toBeInTheDocument();
    expect(field(backend, "Database").getByText("Error")).toBeInTheDocument();
    expect(field(backend, "Database").getByText(/test query to Postgres failed/)).toBeInTheDocument();
  });

  it("names the model when the provider is fable, and still credits signatures with confirmation", async () => {
    answer = { ...fixtures["health.get"], llm_provider: "fable", llm_configured: true, llm_model: "claude-fable-5-2" };
    renderSettings("live");
    const investigations = panel("Investigations");
    await investigations.findByText("Can run");
    expect(field(investigations, "Model").getByText("claude-fable-5-2")).toBeInTheDocument();
    expect(field(investigations, "Can run").getByText("Yes")).toBeInTheDocument();
    expect(field(investigations, "Hypotheses by").getByText(/Only a deterministic signature can mark a root cause confirmed/)).toBeInTheDocument();
  });

  it("warns when the provider is fable but the backend says it cannot run", async () => {
    answer = { ...fixtures["health.get"], llm_provider: "fable", llm_configured: false, llm_model: "claude-fable-5-2" };
    renderSettings("live");
    const investigations = panel("Investigations");
    expect(await investigations.findByText("No: not configured")).toBeInTheDocument();
    expect(field(investigations, "Hypotheses by").getByText(/no API key is set/)).toBeInTheDocument();
  });

  it("shows the API's error and how to start the backend when the health check fails, then recovers on retry", async () => {
    const user = userEvent.setup();
    // What lib/api/live.ts throws when the request gets no answer at all.
    answer = new ApiError("network_error", `Could not reach the Ghostwatch API at ${BASE_URL}. Is the backend running?`);
    renderSettings("live");
    const backend = panel("Backend");
    const alert = await backend.findByRole("alert");
    expect(alert).toHaveTextContent("The backend did not answer the health check");
    expect(alert).toHaveTextContent(`Could not reach the Ghostwatch API at ${BASE_URL}`);
    expect(backend.getByLabelText("Commands that start the backend")).toHaveTextContent("docker compose up -d");
    expect(backend.queryByText("Reachable")).not.toBeInTheDocument();
    // Nothing about the provider is claimed while it is unknown.
    expect(panel("Investigations").getByText(/^Not known/)).toBeInTheDocument();

    answer = fixtures["health.get"];
    const before = calls;
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await backend.findByText("Reachable")).toBeInTheDocument();
    expect(calls).toBeGreaterThan(before);
  });
});
