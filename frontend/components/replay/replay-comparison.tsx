/**
 * A finished replay compared with its original (contract §10).
 *
 * The outcome, the three deltas and every row of the step table are fields of `comparison`,
 * computed by the backend. The only thing counted here is how many replay steps have each
 * `replay_source`, so that an outcome such as `fixed` can be read against what was served from the
 * recording and what really ran.
 */
import Link from "next/link";
import type { ReactNode } from "react";

import { ReplaySourceBadge, StatusBadge, StepChangeBadge, StepStatusBadge } from "@/components/data/badges";
import { Cost, Duration, IdChip, Tokens } from "@/components/data/values";
import {
  REPLAY_SOURCES,
  type ExecutionSummary,
  type ID,
  type Replay,
  type ReplayComparison,
  type ReplayOutcome,
  type ReplaySource,
  type StepDiff,
  type StepStatus,
} from "@/lib/api/types";
import { REPLAY_OUTCOME, TONE_TEXT } from "@/lib/enums";
import { formatCount, formatCountDelta, formatDurationDelta, pluralize } from "@/lib/format";
import { LIVE_RULE, SANDBOX_RULE } from "@/lib/replay";
import { cn } from "@/lib/utils";

/** One frame per outcome. `fixed` is the only one that is filled green. */
const OUTCOME_FRAME: Record<ReplayOutcome, string> = {
  fixed: "border-completed/60 bg-completed/[0.07]",
  regressed: "border-failed/60 bg-failed/[0.06]",
  same_failure: "border-failed/40",
  different_failure: "border-timed-out/50",
  both_succeeded: "border-line",
  inconclusive: "border-dashed border-line",
};

const SOURCE_PHRASE: Record<ReplaySource, (count: number) => string> = {
  recorded: (count) => `${count} served from the recording`,
  executed: (count) => `${count} really ran`,
  blocked: (count) => `${count} blocked`,
};

/** How many replay steps have each source. Steps without a replay step have none. */
export function sourceCounts(diffs: StepDiff[]): Record<ReplaySource, number> {
  const counts: Record<ReplaySource, number> = { recorded: 0, executed: 0, blocked: 0 };
  for (const diff of diffs) if (diff.replay_source) counts[diff.replay_source] += 1;
  return counts;
}

function OutcomeBanner({ replay, comparison }: { replay: Replay; comparison: ReplayComparison }) {
  const meta = REPLAY_OUTCOME[comparison.outcome];
  const Icon = meta.icon;
  const counts = sourceCounts(comparison.step_diffs);
  const replaySteps = comparison.step_diffs.filter((diff) => diff.replay_step_id !== null).length;
  return (
    <section aria-label="Outcome" data-outcome={comparison.outcome} className={cn("flex gap-4 rounded-lg border px-5 py-4", OUTCOME_FRAME[comparison.outcome])}>
      <Icon className={cn("mt-1 size-7 shrink-0", TONE_TEXT[meta.tone])} strokeWidth={1.75} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <h2 className={cn("text-2xl font-semibold tracking-tight", meta.tone === "muted" || meta.tone === "subtle" ? "text-fg" : TONE_TEXT[meta.tone])}>{meta.label}</h2>
        <p className="mt-1 text-sm">{meta.hint}</p>
        <p className="mt-2 max-w-4xl text-xs text-fg-muted" data-testid="replay-sources">
          {replay.mode === "sandbox" ? (
            <>
              <span className="font-medium text-fg">Sandbox replay.</span>{" "}
              {replaySteps === 0
                ? "The replay recorded no steps."
                : `Of the replay's ${pluralize(replaySteps, "step")}: ${REPLAY_SOURCES.map((source) => SOURCE_PHRASE[source](counts[source])).join(", ")}.`}{" "}
              {SANDBOX_RULE}
            </>
          ) : (
            <>
              <span className="font-medium text-timed-out">Live replay, side effects {replay.side_effects_authorized ? "authorized" : "not authorized"}.</span> {LIVE_RULE}
            </>
          )}
        </p>
      </div>
    </section>
  );
}

// ── Original and replay, side by side ───────────────────────────────────────

function Row({ label, original, replay, delta }: { label: string; original: ReactNode; replay: ReactNode; delta?: ReactNode }) {
  return (
    <tr className="border-b border-line-subtle last:border-0">
      <th scope="row" className="w-28 px-4 py-2 text-left text-xs font-normal text-fg-muted">
        {label}
      </th>
      <td className="px-4 py-2">{original}</td>
      <td className="px-4 py-2">{replay}</td>
      <td className="num w-32 px-4 py-2 text-right font-mono text-xs">{delta ?? <span className="sr-only">No difference is reported for this row</span>}</td>
    </tr>
  );
}

const ErrorCell = ({ execution }: { execution: ExecutionSummary }) =>
  execution.error ? (
    <code className="block max-w-md break-words font-mono text-xs">
      <span className="text-failed">{execution.error.type}</span>: {execution.error.message}
    </code>
  ) : (
    <span className="text-fg-subtle">None</span>
  );

function Delta({ text, unknown }: { text: string; unknown: boolean }) {
  return <span className={unknown ? "text-fg-subtle" : undefined}>{text}</span>;
}

function SummaryTable({ comparison }: { comparison: ReplayComparison }) {
  const { original, replay } = comparison;
  return (
    <section aria-label="Original and replay" className="overflow-hidden rounded-lg border border-line-subtle bg-surface">
      <table className="w-full border-collapse">
        <caption className="sr-only">The original execution and the replay, side by side</caption>
        <thead>
          <tr className="border-b border-line-subtle text-left text-xs text-fg-muted">
            <td className="px-4 py-2" />
            <th scope="col" className="px-4 py-2 font-medium">
              Original
            </th>
            <th scope="col" className="px-4 py-2 font-medium">
              Replay
            </th>
            <th scope="col" className="px-4 py-2 text-right font-medium">
              Difference
            </th>
          </tr>
        </thead>
        <tbody>
          <Row label="Status" original={<StatusBadge status={original.status} />} replay={<StatusBadge status={replay.status} />} />
          <Row
            label="Duration"
            original={<Duration ms={original.duration_ms} />}
            replay={<Duration ms={replay.duration_ms} />}
            delta={<Delta text={formatDurationDelta(comparison.duration_delta_ms)} unknown={comparison.duration_delta_ms === null} />}
          />
          <Row
            label="Steps"
            original={<span className="num font-mono text-xs">{formatCount(original.step_count)}</span>}
            replay={<span className="num font-mono text-xs">{formatCount(replay.step_count)}</span>}
            delta={<Delta text={formatCountDelta(comparison.step_count_delta)} unknown={false} />}
          />
          <Row
            label="Tokens"
            original={<Tokens value={original.tokens_total} />}
            replay={<Tokens value={replay.tokens_total} />}
            delta={<Delta text={formatCountDelta(comparison.tokens_delta)} unknown={comparison.tokens_delta === null} />}
          />
          <Row label="Cost" original={<Cost usd={original.cost_usd} />} replay={<Cost usd={replay.cost_usd} />} />
          <Row label="Error" original={<ErrorCell execution={original} />} replay={<ErrorCell execution={replay} />} />
          <Row
            label="Trace"
            original={<IdChip id={original.id} href={`/executions/${original.id}`} />}
            replay={<IdChip id={replay.id} href={`/executions/${replay.id}`} />}
          />
        </tbody>
      </table>
    </section>
  );
}

// ── Step by step ────────────────────────────────────────────────────────────

function StepCell({ status, stepId, executionId, name, side }: { status: StepStatus | null; stepId: ID | null; executionId: ID; name: string; side: "original" | "replay" }) {
  if (status === null || stepId === null) return <span className="text-fg-subtle">Not in the {side}</span>;
  return (
    <Link
      href={`/executions/${executionId}?step=${stepId}`}
      aria-label={`Open step ${name} in the ${side}`}
      className="inline-flex rounded-sm underline-offset-2 hover:underline"
    >
      <StepStatusBadge status={status} />
    </Link>
  );
}

function StepDiffTable({ comparison }: { comparison: ReplayComparison }) {
  const diffs = comparison.step_diffs;
  const changed = diffs.filter((diff) => diff.change !== "unchanged").length;
  return (
    <section aria-labelledby="replay-steps" className="flex flex-col gap-2.5">
      <h2 id="replay-steps" className="flex flex-wrap items-baseline gap-x-2 text-sm font-semibold">
        Steps <span className="font-normal text-fg-muted">· aligned by position and name</span>{" "}
        <span className="num font-mono text-xs font-normal text-fg-subtle">
          {changed} of {diffs.length} differ
        </span>
      </h2>
      {diffs.length === 0 ? (
        <p className="text-fg-muted">Neither run recorded a step.</p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-line-subtle bg-surface">
          <table className="w-full border-collapse">
            <caption className="sr-only">Step-by-step comparison of the original and the replay</caption>
            <thead>
              <tr className="border-b border-line-subtle text-left text-xs text-fg-muted">
                <th scope="col" className="w-12 py-2 pl-4 pr-2 text-right font-medium">
                  #
                </th>
                <th scope="col" className="px-4 py-2 font-medium">
                  Step
                </th>
                <th scope="col" className="w-40 px-4 py-2 font-medium">
                  Original
                </th>
                <th scope="col" className="w-40 px-4 py-2 font-medium">
                  Replay
                </th>
                <th scope="col" className="w-40 px-4 py-2 font-medium">
                  Change
                </th>
                <th scope="col" className="w-36 px-4 py-2 font-medium">
                  In the replay
                </th>
              </tr>
            </thead>
            <tbody>
              {diffs.map((diff) => {
                const differs = diff.change !== "unchanged";
                return (
                  <tr
                    key={`${diff.ordinal}-${diff.name}`}
                    data-change={diff.change}
                    className={cn("border-b border-line-subtle last:border-0", differs && "bg-raised shadow-[inset_2px_0_0_var(--color-fg)]")}
                  >
                    <td className="num py-2 pl-4 pr-2 text-right font-mono text-xs text-fg-subtle">{diff.ordinal}</td>
                    <th scope="row" className={cn("px-4 py-2 text-left font-mono text-xs font-normal", !differs && "text-fg-muted")}>
                      {diff.name}
                    </th>
                    <td className="px-4 py-2">
                      <StepCell status={diff.original_status} stepId={diff.original_step_id} executionId={comparison.original.id} name={diff.name} side="original" />
                    </td>
                    <td className="px-4 py-2">
                      <StepCell status={diff.replay_status} stepId={diff.replay_step_id} executionId={comparison.replay.id} name={diff.name} side="replay" />
                    </td>
                    <td className="px-4 py-2">
                      <StepChangeBadge change={diff.change} />
                    </td>
                    <td className="px-4 py-2">{diff.replay_source ? <ReplaySourceBadge source={diff.replay_source} /> : <span className="text-fg-subtle">—</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function ReplayComparisonView({ replay, comparison }: { replay: Replay; comparison: ReplayComparison }) {
  return (
    <div className="flex flex-col gap-6">
      <OutcomeBanner replay={replay} comparison={comparison} />
      <SummaryTable comparison={comparison} />
      <StepDiffTable comparison={comparison} />
    </div>
  );
}
