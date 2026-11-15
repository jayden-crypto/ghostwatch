import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  AnomalyStatusBadge,
  AnomalyTypeBadge,
  ConfidenceBadge,
  EventTypeLabel,
  EvidenceKindBadge,
  HealthBadge,
  InvestigationStatusBadge,
  OutcomeBadge,
  ProviderBadge,
  ReplayModeBadge,
  ReplayStatusBadge,
  RootCauseBadge,
  SeverityBadge,
  StatusBadge,
  StepChangeBadge,
  StepStatusBadge,
  StepTypeBadge,
  TriggerBadge,
} from "@/components/data/badges";
import { DataTable, Pagination, type Column } from "@/components/data/data-table";
import { JsonViewer } from "@/components/data/json-viewer";
import { ErrorState } from "@/components/data/states";
import { Cost, Duration, Tokens } from "@/components/data/values";
import { ApiError } from "@/lib/api/errors";
import * as T from "@/lib/api/types";
import * as E from "@/lib/enums";

/** Every enum of contract §1 with its badge and its presentation table. */
const ENUMS: [string, readonly string[], Record<string, E.EnumMeta>, (value: never) => ReactElement][] = [
  ["ExecutionStatus", T.EXECUTION_STATUSES, E.EXECUTION_STATUS, (v) => <StatusBadge status={v} />],
  ["StepStatus", T.STEP_STATUSES, E.STEP_STATUS, (v) => <StepStatusBadge status={v} />],
  ["StepType", T.STEP_TYPES, E.STEP_TYPE, (v) => <StepTypeBadge type={v} />],
  ["Severity", T.SEVERITIES, E.SEVERITY, (v) => <SeverityBadge severity={v} />],
  ["AnomalyType", T.ANOMALY_TYPES, E.ANOMALY_TYPE, (v) => <AnomalyTypeBadge type={v} />],
  ["AnomalyStatus", T.ANOMALY_STATUSES, E.ANOMALY_STATUS, (v) => <AnomalyStatusBadge status={v} />],
  ["AgentHealth", T.AGENT_HEALTHS, E.AGENT_HEALTH, (v) => <HealthBadge health={v} />],
  ["InvestigationStatus", T.INVESTIGATION_STATUSES, E.INVESTIGATION_STATUS, (v) => <InvestigationStatusBadge status={v} />],
  ["InvestigationTrigger", T.INVESTIGATION_TRIGGERS, E.INVESTIGATION_TRIGGER, (v) => <TriggerBadge trigger={v} />],
  ["Confidence", T.CONFIDENCES, E.CONFIDENCE, (v) => <ConfidenceBadge confidence={v} />],
  ["RootCauseStatus", T.ROOT_CAUSE_STATUSES, E.ROOT_CAUSE_STATUS, (v) => <RootCauseBadge status={v} />],
  ["EvidenceKind", T.EVIDENCE_KINDS, E.EVIDENCE_KIND, (v) => <EvidenceKindBadge kind={v} />],
  ["ReplayMode", T.REPLAY_MODES, E.REPLAY_MODE, (v) => <ReplayModeBadge mode={v} />],
  ["ReplayStatus", T.REPLAY_STATUSES, E.REPLAY_STATUS, (v) => <ReplayStatusBadge status={v} />],
  ["ReplayOutcome", T.REPLAY_OUTCOMES, E.REPLAY_OUTCOME, (v) => <OutcomeBadge outcome={v} />],
  ["StepChange", T.STEP_CHANGES, E.STEP_CHANGE, (v) => <StepChangeBadge change={v} />],
  ["EventType", T.EVENT_TYPES, E.EVENT_TYPE, (v) => <EventTypeLabel type={v} />],
];

describe("enum badges", () => {
  it.each(ENUMS)("%s: every value has a text label", (_name, values, table, badge) => {
    for (const value of values) {
      const { unmount } = render(badge(value as never));
      expect(screen.getByText(table[value].label)).toBeInTheDocument();
      unmount();
    }
  });

  it("gives each value of an enum a different label", () => {
    for (const [name, values, table] of ENUMS) {
      const labels = values.map((value) => table[value].label);
      expect(new Set(labels).size, name).toBe(labels.length);
    }
  });

  it("names the model for a fable report and says rule-based otherwise", () => {
    const { rerender } = render(<ProviderBadge provider="fable" model="claude-fable-5-2" />);
    expect(screen.getByText("claude-fable-5-2")).toBeInTheDocument();
    rerender(<ProviderBadge provider="rule_based" model={null} />);
    expect(screen.getByText("Rule-based")).toBeInTheDocument();
  });

  it("shows a value the contract does not define verbatim and logs it", () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<StatusBadge status={"cancelled" as T.ExecutionStatus} />);
    expect(screen.getByText("cancelled")).toBeInTheDocument();
    expect(logged).toHaveBeenCalledWith(expect.stringContaining('ExecutionStatus has a value the contract does not define: "cancelled"'));
  });
});

describe("values", () => {
  it("shows unknown as a dash, never as zero", () => {
    render(
      <>
        <Duration ms={null} />
        <Tokens value={null} />
        <Cost usd={null} />
      </>,
    );
    expect(screen.getAllByText("—")).toHaveLength(3);
    expect(screen.queryByText(/0/)).not.toBeInTheDocument();
  });

  it("formats known values", () => {
    render(
      <>
        <Duration ms={12_400} />
        <Tokens value={45_812} />
        <Cost usd={0.0123} />
      </>,
    );
    expect(screen.getByText("12.4 s")).toBeInTheDocument();
    expect(screen.getByText("45,812")).toBeInTheDocument();
    expect(screen.getByText("$0.0123")).toBeInTheDocument();
  });
});

describe("JsonViewer", () => {
  it("renders nested values and collapses and expands them", async () => {
    const user = userEvent.setup();
    render(<JsonViewer value={{ query: "trace", nested: { deep: { hidden: 42 } }, list: [] }} expandDepth={2} />);
    expect(screen.getByText('"trace"')).toBeInTheDocument();
    expect(screen.getByText("1 key")).toBeInTheDocument(); // `deep` starts collapsed at depth 2
    expect(screen.queryByText("42")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Expand deep" }));
    expect(screen.getByText("42")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Collapse nested" }));
    expect(screen.queryByText("42")).not.toBeInTheDocument();
  });

  it("renders null as null, not as empty", () => {
    render(<JsonViewer value={null} />);
    expect(screen.getByText("null")).toBeInTheDocument();
  });

  it("announces a truncated payload with its original size and shows only the preview", () => {
    render(<JsonViewer value={{ _truncated: true, original_bytes: 186_368, preview: '{"results":[{"title":"Schema' }} />);
    const banner = screen.getByRole("note");
    expect(within(banner).getByText("Payload truncated — 182 KB")).toBeInTheDocument();
    expect(within(banner).getByText(/186,368 bytes/)).toBeInTheDocument();
    expect(screen.getByText(/\{"results":\[\{"title":"Schema/)).toBeInTheDocument();
    expect(screen.queryByText('"_truncated"')).not.toBeInTheDocument();
  });

  it("pages through a large array instead of rendering it all", async () => {
    const user = userEvent.setup();
    render(<JsonViewer value={Array.from({ length: 250 }, (_, i) => i)} />);
    expect(screen.getByText("99")).toBeInTheDocument();
    expect(screen.queryByText("100")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Show 100 more of 150 remaining/ }));
    expect(screen.getByText("199")).toBeInTheDocument();
  });
});

describe("DataTable", () => {
  interface Row {
    id: string;
    name: string;
    ms: number;
  }
  const columns: Column<Row>[] = [
    { id: "name", header: "Name", cell: (row) => row.name },
    { id: "ms", header: "Duration", cell: (row) => row.ms, align: "right", sortKey: "duration_ms" },
  ];
  const rows: Row[] = [
    { id: "a", name: "alpha", ms: 10 },
    { id: "b", name: "beta", ms: 20 },
  ];

  it("shows skeleton rows while loading and the empty slot when there is nothing", () => {
    const { rerender } = render(<DataTable columns={columns} rows={undefined} rowKey={(r) => r.id} empty={<p>Nothing here</p>} caption="Rows" skeletonRows={3} />);
    expect(screen.getAllByRole("row")).toHaveLength(4);
    rerender(<DataTable columns={columns} rows={[]} rowKey={(r) => r.id} empty={<p>Nothing here</p>} caption="Rows" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("links each row and reports sort changes in the contract's form", async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    const { rerender } = render(
      <DataTable columns={columns} rows={rows} rowKey={(r) => r.id} rowHref={(r) => `/x/${r.id}`} rowLabel={(r) => `Open ${r.name}`} sort="-started_at" onSortChange={onSortChange} empty={null} caption="Rows" />,
    );
    expect(screen.getByRole("link", { name: "Open alpha" })).toHaveAttribute("href", "/x/a");
    await user.click(screen.getByRole("button", { name: "Duration" }));
    expect(onSortChange).toHaveBeenLastCalledWith("-duration_ms");
    rerender(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} sort="-duration_ms" onSortChange={onSortChange} empty={null} caption="Rows" />);
    expect(screen.getByRole("columnheader", { name: "Duration" })).toHaveAttribute("aria-sort", "descending");
    await user.click(screen.getByRole("button", { name: "Duration" }));
    expect(onSortChange).toHaveBeenLastCalledWith("duration_ms");
  });

  it("paginates by offset", async () => {
    const user = userEvent.setup();
    const onOffsetChange = vi.fn();
    render(<Pagination total={213} limit={50} offset={50} onOffsetChange={onOffsetChange} noun="executions" />);
    expect(screen.getByText("51–100 of 213 executions")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(onOffsetChange).toHaveBeenLastCalledWith(100);
    await user.click(screen.getByRole("button", { name: "Previous page" }));
    expect(onOffsetChange).toHaveBeenLastCalledWith(0);
  });
});

describe("ErrorState", () => {
  it("shows the API's message and code and retries", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ErrorState error={new ApiError("not_found", "Execution exe_1 does not exist.", 404)} onRetry={onRetry} />);
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("Execution exe_1 does not exist.")).toBeInTheDocument();
    expect(within(alert).getByText("not_found · HTTP 404")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
