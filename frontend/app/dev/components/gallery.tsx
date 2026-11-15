"use client";

import { Inbox } from "lucide-react";
import type { ReactNode } from "react";

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
import { EmptyState } from "@/components/data/empty-state";
import { JsonViewer } from "@/components/data/json-viewer";
import { ErrorState, Panel, StatTile, StatTileSkeleton } from "@/components/data/states";
import { Cost, Duration, IdChip, Timestamp, Tokens } from "@/components/data/values";
import { Page } from "@/components/shell/page";
import { ApiError } from "@/lib/api/errors";
import {
  AGENT_HEALTHS,
  ANOMALY_STATUSES,
  ANOMALY_TYPES,
  CONFIDENCES,
  EVENT_TYPES,
  EVIDENCE_KINDS,
  EXECUTION_STATUSES,
  INVESTIGATION_PROVIDERS,
  INVESTIGATION_STATUSES,
  INVESTIGATION_TRIGGERS,
  REPLAY_MODES,
  REPLAY_OUTCOMES,
  REPLAY_STATUSES,
  ROOT_CAUSE_STATUSES,
  SEVERITIES,
  STEP_CHANGES,
  STEP_STATUSES,
  STEP_TYPES,
} from "@/lib/api/types";

function Row({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline gap-4 border-b border-line-subtle py-2.5 last:border-0">
      <span className="w-44 shrink-0 font-mono text-xs text-fg-subtle">{name}</span>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">{children}</div>
    </div>
  );
}

const SAMPLE = {
  query: "how do teams trace what an ai agent did",
  max_results: 3,
  cached: false,
  cursor: null,
  results: [{ title: "Agent observability: tracing every step", score: 0.92 }],
  empty: {},
};

const TRUNCATED = {
  _truncated: true,
  original_bytes: 186_368,
  preview: '{"results":[{"title":"Schema drift in upstream APIs (part 1)","url":"https://example.test/schema-drift","snippet":"A renamed response field breaks every consumer',
};

export function Gallery() {
  return (
    <Page title="Component gallery" description="Development reference: every enum badge and the shared states. The values below are samples, not data.">
      <Panel title="Enum badges (contract §1)">
        <Row name="ExecutionStatus">{EXECUTION_STATUSES.map((v) => <StatusBadge key={v} status={v} />)}</Row>
        <Row name="StepStatus">{STEP_STATUSES.map((v) => <StepStatusBadge key={v} status={v} />)}</Row>
        <Row name="StepType">{STEP_TYPES.map((v) => <StepTypeBadge key={v} type={v} />)}</Row>
        <Row name="Severity">{SEVERITIES.map((v) => <SeverityBadge key={v} severity={v} />)}</Row>
        <Row name="AnomalyType">{ANOMALY_TYPES.map((v) => <AnomalyTypeBadge key={v} type={v} />)}</Row>
        <Row name="AnomalyStatus">{ANOMALY_STATUSES.map((v) => <AnomalyStatusBadge key={v} status={v} />)}</Row>
        <Row name="AgentHealth">{AGENT_HEALTHS.map((v) => <HealthBadge key={v} health={v} />)}</Row>
        <Row name="InvestigationStatus">{INVESTIGATION_STATUSES.map((v) => <InvestigationStatusBadge key={v} status={v} />)}</Row>
        <Row name="InvestigationTrigger">{INVESTIGATION_TRIGGERS.map((v) => <TriggerBadge key={v} trigger={v} />)}</Row>
        <Row name="InvestigationProvider">
          {INVESTIGATION_PROVIDERS.map((v) => <ProviderBadge key={v} provider={v} model={v === "fable" ? "claude-fable-5-2" : null} />)}
        </Row>
        <Row name="Confidence">{CONFIDENCES.map((v) => <ConfidenceBadge key={v} confidence={v} />)}</Row>
        <Row name="RootCauseStatus">{ROOT_CAUSE_STATUSES.map((v) => <RootCauseBadge key={v} status={v} />)}</Row>
        <Row name="EvidenceKind">{EVIDENCE_KINDS.map((v) => <EvidenceKindBadge key={v} kind={v} />)}</Row>
        <Row name="ReplayMode">{REPLAY_MODES.map((v) => <ReplayModeBadge key={v} mode={v} />)}</Row>
        <Row name="ReplayStatus">{REPLAY_STATUSES.map((v) => <ReplayStatusBadge key={v} status={v} />)}</Row>
        <Row name="ReplayOutcome">{REPLAY_OUTCOMES.map((v) => <OutcomeBadge key={v} outcome={v} />)}</Row>
        <Row name="StepChange">{STEP_CHANGES.map((v) => <StepChangeBadge key={v} change={v} />)}</Row>
        <Row name="EventType">{EVENT_TYPES.map((v) => <EventTypeLabel key={v} type={v} />)}</Row>
      </Panel>

      <Panel title="Values">
        <Row name="Duration">
          {[842, 12_400, 185_000, 3_720_000, null].map((ms, i) => <Duration key={i} ms={ms} />)}
        </Row>
        <Row name="Tokens">
          <Tokens value={45_812} />
          <Tokens value={null} />
        </Row>
        <Row name="Cost">
          <Cost usd={0.0123} />
          <Cost usd={null} />
        </Row>
        <Row name="Timestamp">
          <Timestamp value="2026-11-14T17:20:14.592Z" />
          <Timestamp value="2026-11-14T17:20:14.592Z" mode="utc" />
          <Timestamp value="2026-11-14T17:20:14.592Z" mode="time" />
          <Timestamp value={null} />
        </Row>
        <Row name="IdChip">
          <IdChip id="exe_3f9c2a7e1b4d4e0f9a8b7c6d5e4f3a2b" />
          <IdChip id="exe_3f9c2a7e1b4d4e0f9a8b7c6d5e4f3a2b" href="/executions" />
        </Row>
      </Panel>

      <div className="grid grid-cols-2 gap-6">
        <Panel title="JsonViewer">
          <JsonViewer value={SAMPLE} />
        </Panel>
        <Panel title="JsonViewer · truncated payload">
          <JsonViewer value={TRUNCATED} />
        </Panel>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <StatTile label="Executions" value="41" detail="last 7 days" />
        <StatTile label="Success rate" value="80%" detail="32 of 40 finished" />
        <StatTile label="Avg duration" value="—" detail="no finished runs" />
        <StatTileSkeleton />
      </div>

      <div className="grid grid-cols-2 gap-6">
        <EmptyState
          icon={Inbox}
          title="No executions yet"
          description="Runs appear here as soon as an agent reports one."
          command="uv run python demo/seed.py"
        />
        <ErrorState
          error={new ApiError("network_error", "Could not reach the Ghostwatch API at http://localhost:8000/api/v1. Is the backend running?")}
          onRetry={() => undefined}
        />
      </div>
    </Page>
  );
}
