/**
 * One badge per contract enum. Every badge is an icon plus a text label, so colour is never the
 * only signal. Presentation comes from lib/enums.ts.
 */
import type {
  AgentHealth,
  AnomalyStatus,
  AnomalyType,
  Confidence,
  EventType,
  EvidenceKind,
  ExecutionStatus,
  InvestigationProvider,
  InvestigationStatus,
  InvestigationTrigger,
  ReplayMode,
  ReplayOutcome,
  ReplayStatus,
  RootCauseStatus,
  Severity,
  StepChange,
  StepStatus,
  StepType,
} from "@/lib/api/types";
import {
  AGENT_HEALTH,
  ANOMALY_STATUS,
  ANOMALY_TYPE,
  CONFIDENCE,
  EVENT_TYPE,
  EVIDENCE_KIND,
  EXECUTION_STATUS,
  INVESTIGATION_PROVIDER,
  INVESTIGATION_STATUS,
  INVESTIGATION_TRIGGER,
  metaOf,
  REPLAY_MODE,
  REPLAY_OUTCOME,
  REPLAY_STATUS,
  ROOT_CAUSE_STATUS,
  SEVERITY,
  STEP_CHANGE,
  STEP_STATUS,
  STEP_TYPE,
  TONE_BG,
  TONE_TEXT,
  type EnumMeta,
  type Tone,
} from "@/lib/enums";
import { cn } from "@/lib/utils";

const CHROME: ReadonlySet<Tone> = new Set(["fg", "muted", "subtle"]);

interface BadgeProps {
  className?: string;
  /** Show the icon alone; the label stays available to screen readers and as a tooltip. */
  iconOnly?: boolean;
}

function EnumBadge({ meta, className, iconOnly, enumName }: BadgeProps & { meta: EnumMeta; enumName: string }) {
  const Icon = meta.icon;
  // A tone that carries meaning colours the label too; a chrome tone leaves the label in body text.
  const labelTone = CHROME.has(meta.tone) ? (meta.tone === "subtle" ? "text-fg-subtle" : "text-fg-muted") : TONE_TEXT[meta.tone];
  return (
    <span
      data-enum={enumName}
      title={meta.hint ?? (iconOnly ? meta.label : undefined)}
      className={cn("inline-flex items-center gap-1.5 whitespace-nowrap align-middle", labelTone, className)}
    >
      <Icon
        aria-hidden="true"
        strokeWidth={2}
        className={cn("size-3.5 shrink-0", TONE_TEXT[meta.tone], meta.spin && "animate-spin [animation-duration:1.4s]")}
      />
      <span className={iconOnly ? "sr-only" : undefined}>{meta.label}</span>
    </span>
  );
}

export const StatusBadge = ({ status, ...props }: BadgeProps & { status: ExecutionStatus }) => (
  <EnumBadge meta={metaOf(EXECUTION_STATUS, status, "ExecutionStatus")} enumName="ExecutionStatus" {...props} />
);

export const StepStatusBadge = ({ status, ...props }: BadgeProps & { status: StepStatus }) => (
  <EnumBadge meta={metaOf(STEP_STATUS, status, "StepStatus")} enumName="StepStatus" {...props} />
);

export const StepTypeBadge = ({ type, ...props }: BadgeProps & { type: StepType }) => (
  <EnumBadge meta={metaOf(STEP_TYPE, type, "StepType")} enumName="StepType" {...props} />
);

export const AnomalyTypeBadge = ({ type, ...props }: BadgeProps & { type: AnomalyType }) => (
  <EnumBadge meta={metaOf(ANOMALY_TYPE, type, "AnomalyType")} enumName="AnomalyType" {...props} />
);

export const AnomalyStatusBadge = ({ status, ...props }: BadgeProps & { status: AnomalyStatus }) => (
  <EnumBadge meta={metaOf(ANOMALY_STATUS, status, "AnomalyStatus")} enumName="AnomalyStatus" {...props} />
);

export const HealthBadge = ({ health, ...props }: BadgeProps & { health: AgentHealth }) => (
  <EnumBadge meta={metaOf(AGENT_HEALTH, health, "AgentHealth")} enumName="AgentHealth" {...props} />
);

export const InvestigationStatusBadge = ({ status, ...props }: BadgeProps & { status: InvestigationStatus }) => (
  <EnumBadge meta={metaOf(INVESTIGATION_STATUS, status, "InvestigationStatus")} enumName="InvestigationStatus" {...props} />
);

export const TriggerBadge = ({ trigger, ...props }: BadgeProps & { trigger: InvestigationTrigger }) => (
  <EnumBadge meta={metaOf(INVESTIGATION_TRIGGER, trigger, "InvestigationTrigger")} enumName="InvestigationTrigger" {...props} />
);

export const RootCauseBadge = ({ status, ...props }: BadgeProps & { status: RootCauseStatus }) => (
  <EnumBadge meta={metaOf(ROOT_CAUSE_STATUS, status, "RootCauseStatus")} enumName="RootCauseStatus" {...props} />
);

export const EvidenceKindBadge = ({ kind, ...props }: BadgeProps & { kind: EvidenceKind }) => (
  <EnumBadge meta={metaOf(EVIDENCE_KIND, kind, "EvidenceKind")} enumName="EvidenceKind" {...props} />
);

export const ReplayModeBadge = ({ mode, ...props }: BadgeProps & { mode: ReplayMode }) => (
  <EnumBadge meta={metaOf(REPLAY_MODE, mode, "ReplayMode")} enumName="ReplayMode" {...props} />
);

export const ReplayStatusBadge = ({ status, ...props }: BadgeProps & { status: ReplayStatus }) => (
  <EnumBadge meta={metaOf(REPLAY_STATUS, status, "ReplayStatus")} enumName="ReplayStatus" {...props} />
);

export const OutcomeBadge = ({ outcome, ...props }: BadgeProps & { outcome: ReplayOutcome }) => (
  <EnumBadge meta={metaOf(REPLAY_OUTCOME, outcome, "ReplayOutcome")} enumName="ReplayOutcome" {...props} />
);

export const StepChangeBadge = ({ change, ...props }: BadgeProps & { change: StepChange }) => (
  <EnumBadge meta={metaOf(STEP_CHANGE, change, "StepChange")} enumName="StepChange" {...props} />
);

/**
 * Who produced a report's hypotheses, stated truthfully: the model's id when a model answered,
 * "Rule-based" when none did.
 */
export function ProviderBadge({ provider, model, className }: { provider: InvestigationProvider; model: string | null; className?: string }) {
  const meta = metaOf(INVESTIGATION_PROVIDER, provider, "InvestigationProvider");
  const Icon = meta.icon;
  return (
    <span data-enum="InvestigationProvider" title={meta.hint} className={cn("inline-flex items-center gap-1.5 whitespace-nowrap text-fg-muted", className)}>
      <Icon aria-hidden="true" className="size-3.5 shrink-0" />
      {provider === "fable" && model ? <span className="font-mono text-xs">{model}</span> : <span>{meta.label}</span>}
    </span>
  );
}

/** Severity as one to four bars plus the word. */
export function SeverityBadge({ severity, className, iconOnly }: BadgeProps & { severity: Severity }) {
  const meta = metaOf(SEVERITY, severity, "Severity");
  const rank = "rank" in meta ? meta.rank : 0;
  return (
    <span data-enum="Severity" title={iconOnly ? meta.label : undefined} className={cn("inline-flex items-center gap-1.5 whitespace-nowrap", TONE_TEXT[meta.tone], className)}>
      <span aria-hidden="true" className="flex items-end gap-px">
        {[1, 2, 3, 4].map((bar) => (
          <span
            key={bar}
            className={cn("w-[3px] rounded-[1px]", bar <= rank ? TONE_BG[meta.tone] : "bg-line")}
            style={{ height: 3 + bar * 2.5 }}
          />
        ))}
      </span>
      <span className={iconOnly ? "sr-only" : undefined}>{meta.label}</span>
    </span>
  );
}

/** Confidence as three segments plus the words. Never a percentage: the contract has three levels. */
export function ConfidenceBadge({ confidence, className }: { confidence: Confidence; className?: string }) {
  const meta = metaOf(CONFIDENCE, confidence, "Confidence");
  const level = "level" in meta ? meta.level : 0;
  return (
    <span data-enum="Confidence" className={cn("inline-flex items-center gap-2 whitespace-nowrap text-fg-muted", className)}>
      <span aria-hidden="true" className="flex gap-0.5">
        {[1, 2, 3].map((segment) => (
          <span key={segment} className={cn("h-1.5 w-3 rounded-[1px]", segment <= level ? "bg-fg-muted" : "bg-line")} />
        ))}
      </span>
      {meta.label}
    </span>
  );
}

/** An event type as recorded, in mono. */
export function EventTypeLabel({ type, className }: { type: EventType; className?: string }) {
  const meta = metaOf(EVENT_TYPE, type, "EventType");
  return (
    <span data-enum="EventType" className={cn("whitespace-nowrap font-mono text-xs", TONE_TEXT[meta.tone], className)}>
      {meta.label}
    </span>
  );
}
