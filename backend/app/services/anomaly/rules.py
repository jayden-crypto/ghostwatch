"""The eight deterministic anomaly rules (contract §8).

Each rule is a pure function of stored data. It returns a draft, or None when it does not fire.
Explanations are templates that state the observed value, the baseline figures and the threshold
formula. Evidence items point at real rows and copy their values: nothing here is generated.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models import Execution, Step
from app.services.anomaly import thresholds as t
from app.services.anomaly.baseline import Baseline, RecentRun
from app.services.executions import tokens_total
from app.timeutil import format_timestamp


@dataclass(frozen=True)
class AnomalyDraft:
    type: str
    severity: str
    title: str
    explanation: str
    evidence: list[dict[str, Any]]

    @property
    def rule_id(self) -> str:
        return f"{self.type}.v1"


@dataclass(frozen=True)
class StaleInfo:
    """Set by the sweeper when it times out an execution that stopped sending events."""

    last_event_at: datetime
    timeout_ms: int
    idle_ms: int


@dataclass(frozen=True)
class RuleInput:
    execution: Execution
    steps: Sequence[Step]
    baseline: Baseline
    recent_runs: Sequence[RecentRun]  # newest first; the first one is this execution
    agent_slug: str
    stale: StaleInfo | None = None


def _evidence(
    kind: str,
    label: str,
    *,
    ref_id: str | None = None,
    field: str | None = None,
    observed: Any = None,
    expected: Any = None,
    excerpt: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "ref_id": ref_id,
        "field": field,
        "observed": observed,
        "expected": expected,
        "excerpt": None if excerpt is None else excerpt[:500],
    }


def _number(value: float) -> str:
    """12,400 for whole numbers, 12,400.5 otherwise."""
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"


def _plural(count: int, noun: str, plural: str | None = None) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {plural or noun + 's'}"


def _step_label(step: Step) -> str:
    attempt = f" (attempt {step.attempt})" if step.attempt > 1 else ""
    return f"Step {step.ordinal} {step.name}{attempt}"


def _failed_step_evidence(step: Step) -> dict[str, Any]:
    error = step.error or {}
    return _evidence(
        "step",
        f"{_step_label(step)} failed",
        ref_id=step.id,
        field="error.message",
        observed=error.get("message"),
        excerpt=error.get("message"),
    )


def _spike(
    *,
    anomaly_type: str,
    quantity: str,
    unit: str,
    field: str,
    observed: int,
    values: list[int],
    median: float,
    p95: int,
    median_factor: float,
    p95_factor: float,
    high_factor: float,
    rule_input: RuleInput,
) -> AnomalyDraft | None:
    threshold = max(median_factor * median, p95_factor * p95)
    if observed <= threshold:
        return None
    severity = "high" if observed > high_factor * median else "medium"
    p95_term = "p95" if p95_factor == 1 else f"{_number(p95_factor)}× p95"
    title = (
        f"{quantity.capitalize()} {observed / median:.1f}× above baseline"
        if median > 0
        else f"{quantity.capitalize()} above a zero baseline"
    )
    verb = "took" if unit == "ms" else "used"
    return AnomalyDraft(
        type=anomaly_type,
        severity=severity,
        title=title,
        explanation=(
            f"Execution {verb} {_number(observed)} {unit}. Baseline median for {rule_input.agent_slug} is "
            f"{_number(median)} {unit} over {_plural(len(values), 'run')} (p95 {_number(p95)} {unit}). "
            f"Rule fires above max({_number(median_factor)}× median, {p95_term}) = "
            f"{_number(threshold)} {unit}. "
            f"Severity is high above {_number(high_factor)}× median = {_number(high_factor * median)} {unit}."
        ),
        evidence=[
            _evidence(
                "execution",
                f"{quantity.capitalize()} of this execution",
                ref_id=rule_input.execution.id,
                field=field,
                observed=observed,
                expected=threshold,
            ),
            _evidence(
                "baseline",
                f"Baseline {quantity} over {_plural(len(values), 'completed run')}",
                field=field,
                observed={"median": median, "p95": p95, "runs": len(values)},
            ),
        ],
    )


def duration_spike(rule_input: RuleInput) -> AnomalyDraft | None:
    duration, baseline = rule_input.execution.duration_ms, rule_input.baseline
    if duration is None or not baseline.is_sufficient:
        return None
    return _spike(
        anomaly_type="duration_spike",
        quantity="duration",
        unit="ms",
        field="duration_ms",
        observed=duration,
        values=baseline.durations_ms,
        median=baseline.duration_median,
        p95=baseline.duration_p95,
        median_factor=t.DURATION_SPIKE_MEDIAN_FACTOR,
        p95_factor=t.DURATION_SPIKE_P95_FACTOR,
        high_factor=t.DURATION_SPIKE_HIGH_MEDIAN_FACTOR,
        rule_input=rule_input,
    )


def token_spike(rule_input: RuleInput) -> AnomalyDraft | None:
    total, baseline = tokens_total(rule_input.execution), rule_input.baseline
    if total is None or not baseline.has_token_baseline:
        return None
    return _spike(
        anomaly_type="token_spike",
        quantity="token usage",
        unit="tokens",
        field="tokens_total",
        observed=total,
        values=baseline.token_totals,
        median=baseline.token_median,
        p95=baseline.token_p95,
        median_factor=t.TOKEN_SPIKE_MEDIAN_FACTOR,
        p95_factor=t.TOKEN_SPIKE_P95_FACTOR,
        high_factor=t.TOKEN_SPIKE_HIGH_MEDIAN_FACTOR,
        rule_input=rule_input,
    )


def repeated_tool_failure(rule_input: RuleInput) -> AnomalyDraft | None:
    failed_steps = [step for step in rule_input.steps if step.status == "failed" and step.tool_name]
    counts = Counter(step.tool_name for step in failed_steps)

    within = sorted(tool for tool, count in counts.items() if count >= t.TOOL_FAILURES_IN_ONE_EXECUTION)
    if within:
        tool = within[0]
        steps = [step for step in failed_steps if step.tool_name == tool]
        return AnomalyDraft(
            type="repeated_tool_failure",
            severity="high",
            title=f"Tool {tool} failed {len(steps)} times in one execution"[:80],
            explanation=(
                f"Tool {tool} has {len(steps)} failed steps in this execution. Rule fires at "
                f"{t.TOOL_FAILURES_IN_ONE_EXECUTION} or more failed steps of the same tool in one execution."
            ),
            evidence=[_failed_step_evidence(step) for step in steps[: t.MAX_EVIDENCE_ITEMS]],
        )

    streak = rule_input.recent_runs[: t.TOOL_FAILURE_CONSECUTIVE_EXECUTIONS]
    if len(streak) < t.TOOL_FAILURE_CONSECUTIVE_EXECUTIONS:
        return None
    common = sorted(frozenset.intersection(*(run.failed_tools for run in streak)))
    if not common:
        return None
    tool = common[0]
    return AnomalyDraft(
        type="repeated_tool_failure",
        severity="high",
        title=f"Tool {tool} failed in {len(streak)} executions in a row"[:80],
        explanation=(
            f"The last {len(streak)} executions of {rule_input.agent_slug}, including this one, each have a "
            f"failed step of tool {tool}. Rule fires when the agent's last "
            f"{t.TOOL_FAILURE_CONSECUTIVE_EXECUTIONS} executions all failed on a step with the same tool."
        ),
        evidence=[
            *[_failed_step_evidence(step) for step in failed_steps if step.tool_name == tool][
                : t.MAX_EVIDENCE_ITEMS - 2
            ],
            *[
                _evidence(
                    "execution",
                    f"Earlier execution with a failed {tool} step",
                    ref_id=run.execution_id,
                    field="status",
                    observed=run.status,
                )
                for run in streak[1:]
            ],
        ],
    )


def excessive_retries(rule_input: RuleInput) -> AnomalyDraft | None:
    retried = [step for step in rule_input.steps if step.attempt > 1]
    highest = max((step.attempt for step in retried), default=1)
    total = sum(step.attempt - 1 for step in rule_input.steps)
    if highest < t.RETRY_ATTEMPT_LIMIT and total < t.RETRY_TOTAL_LIMIT:
        return None
    return AnomalyDraft(
        type="excessive_retries",
        severity="medium",
        title=f"{_plural(total, 'retry', 'retries')} in one execution, up to attempt {highest}",
        explanation=(
            f"The highest attempt number in this execution is {highest} and the sum of (attempt - 1) over "
            f"all steps is {total}. Rule fires when any step has attempt >= {t.RETRY_ATTEMPT_LIMIT} or the "
            f"sum is >= {t.RETRY_TOTAL_LIMIT}."
        ),
        evidence=[
            _evidence(
                "step",
                f"{_step_label(step)} is a retry",
                ref_id=step.id,
                field="attempt",
                observed=step.attempt,
                expected=f"below {t.RETRY_ATTEMPT_LIMIT}",
            )
            for step in sorted(retried, key=lambda step: (-step.attempt, step.ordinal))[
                : t.MAX_EVIDENCE_ITEMS
            ]
        ],
    )


def repeated_timeouts(rule_input: RuleInput) -> AnomalyDraft | None:
    window = rule_input.recent_runs[: t.TIMEOUTS_WINDOW]
    timed_out = [run for run in window if run.status == "timed_out"]
    # Raised on the execution that is itself a timeout, so a later healthy run does not re-raise it.
    if rule_input.execution.status != "timed_out" or len(timed_out) < t.TIMEOUTS_LIMIT:
        return None
    return AnomalyDraft(
        type="repeated_timeouts",
        severity="high",
        title=f"{len(timed_out)} of the last {len(window)} executions timed out",
        explanation=(
            f"{len(timed_out)} of the last {len(window)} executions of {rule_input.agent_slug} timed out, "
            f"including this one. Rule fires at {t.TIMEOUTS_LIMIT} or more timeouts in the agent's last "
            f"{t.TIMEOUTS_WINDOW} executions."
        ),
        evidence=[
            _evidence(
                "execution",
                "This execution timed out"
                if run.execution_id == rule_input.execution.id
                else "Earlier timed-out execution",
                ref_id=run.execution_id,
                field="status",
                observed="timed_out",
            )
            for run in timed_out
        ],
    )


def ghost_completion(rule_input: RuleInput) -> AnomalyDraft | None:
    """The agent says it finished; the recorded steps say it did not."""
    execution, steps = rule_input.execution, rule_input.steps
    if execution.status != "completed":
        return None
    reasons: list[str] = []
    evidence: list[dict[str, Any]] = []

    if not steps:
        reasons.append("no steps were recorded")
        evidence.append(
            _evidence(
                "execution",
                "Execution completed without recording any step",
                ref_id=execution.id,
                field="step_count",
                observed=0,
                expected="at least 1",
            )
        )

    completed_names = [step.name for step in steps if step.status == "completed"]
    expected_steps = execution.config.get("expected_steps") or []
    missing = [name for name in dict.fromkeys(expected_steps) if name not in completed_names]
    for name in missing:
        attempts = [step for step in steps if step.name == name]
        if attempts:
            last = attempts[-1]
            evidence.append(
                _evidence(
                    "step",
                    f"Expected step {name} never completed (last seen as {last.status})",
                    ref_id=last.id,
                    field="status",
                    observed=last.status,
                    expected="completed",
                )
            )
        else:
            evidence.append(
                _evidence(
                    "execution",
                    f"Expected step {name} never started",
                    ref_id=execution.id,
                    field="config.expected_steps",
                    observed=list(dict.fromkeys(completed_names)),
                    expected=expected_steps,
                )
            )
    if missing:
        reasons.append(f"expected {_plural(len(missing), 'step')} never completed: {', '.join(missing)}")

    running = [step for step in steps if step.status == "running"]
    for step in running:
        evidence.append(
            _evidence(
                "step",
                f"{_step_label(step)} was still running when the execution completed",
                ref_id=step.id,
                field="status",
                observed="running",
                expected="completed",
            )
        )
    if running:
        reasons.append(
            f"{_plural(len(running), 'step')} still running: {', '.join(step.name for step in running)}"
        )

    if not reasons:
        return None
    if missing:
        title = f"Reported completed, but {missing[0]} never completed"
    elif running:
        title = f"Reported completed while {running[0].name} was still running"
    else:
        title = "Reported completed without recording any step"
    return AnomalyDraft(
        type="ghost_completion",
        severity="critical",
        title=title if len(title) <= 80 else "Reported completed, but the recorded steps do not show it",
        explanation=(
            f"The execution reported status completed, but {'; '.join(reasons)}. Rule fires when a completed "
            "execution has a step still running, an expected step (config.expected_steps) with no completed "
            "step, or no steps at all."
        ),
        evidence=evidence[: t.MAX_EVIDENCE_ITEMS],
    )


def stale_execution(rule_input: RuleInput) -> AnomalyDraft | None:
    stale = rule_input.stale
    if stale is None:
        return None
    return AnomalyDraft(
        type="stale_execution",
        severity="high",
        title=f"No event for {_number(stale.idle_ms)} ms; marked timed out",
        explanation=(
            f"The execution was running and sent no event for {_number(stale.idle_ms)} ms "
            f"(last event received at "
            f"{format_timestamp(stale.last_event_at)}). Rule fires after config.timeout_ms = "
            f"{_number(stale.timeout_ms)} ms without an event; Ghostwatch then marked the execution "
            "timed_out."
        ),
        evidence=[
            _evidence(
                "execution",
                "Time since the last event was received",
                ref_id=rule_input.execution.id,
                field="last_event_at",
                observed={"last_event_at": format_timestamp(stale.last_event_at), "idle_ms": stale.idle_ms},
                expected={"timeout_ms": stale.timeout_ms},
            )
        ],
    )


def unexpected_pattern(rule_input: RuleInput) -> AnomalyDraft | None:
    baseline, steps = rule_input.baseline, rule_input.steps
    if not baseline.is_sufficient:
        return None
    reasons: list[str] = []
    evidence: list[dict[str, Any]] = []

    new_tool_steps = [step for step in steps if step.tool_name and step.tool_name not in baseline.tool_names]
    new_tools = list(dict.fromkeys(step.tool_name for step in new_tool_steps))
    if new_tools:
        reasons.append(
            f"it called {_plural(len(new_tools), 'tool')} never seen in the baseline: {', '.join(new_tools)} "
            f"(baseline tools: {', '.join(sorted(baseline.tool_names)) or 'none'})"
        )
        seen: set[str] = set()
        for step in new_tool_steps:
            if step.tool_name not in seen:
                seen.add(step.tool_name)
                evidence.append(
                    _evidence(
                        "step",
                        f"{_step_label(step)} calls a tool not seen in the baseline",
                        ref_id=step.id,
                        field="tool_name",
                        observed=step.tool_name,
                        expected=sorted(baseline.tool_names),
                    )
                )

    step_limit = t.STEP_COUNT_FACTOR * baseline.max_step_count
    step_count = rule_input.execution.step_count
    if step_count > step_limit:
        reasons.append(
            f"it recorded {_plural(step_count, 'step')}, above {t.STEP_COUNT_FACTOR}× the largest baseline "
            f"step count ({baseline.max_step_count}) = {step_limit}"
        )
        evidence.append(
            _evidence(
                "execution",
                "Number of steps in this execution",
                ref_id=rule_input.execution.id,
                field="step_count",
                observed=step_count,
                expected=step_limit,
            )
        )

    if not reasons:
        return None
    title = (
        f"New tool in this run: {new_tools[0]}"
        if new_tools
        else f"{step_count} steps, baseline maximum is {baseline.max_step_count}"
    )
    return AnomalyDraft(
        type="unexpected_pattern",
        severity="low",
        title=title if len(title) <= 80 else "Step pattern differs from the baseline",
        explanation=(
            f"Compared with the last {_plural(baseline.runs, 'completed run')} of {rule_input.agent_slug}, "
            f"{' and '.join(reasons)}. Rule fires on a tool never seen in the baseline or on step_count "
            "above "
            f"{t.STEP_COUNT_FACTOR}× the baseline maximum."
        ),
        evidence=evidence[: t.MAX_EVIDENCE_ITEMS],
    )


RULES: tuple[Callable[[RuleInput], AnomalyDraft | None], ...] = (
    duration_spike,
    token_spike,
    repeated_tool_failure,
    excessive_retries,
    repeated_timeouts,
    ghost_completion,
    stale_execution,
    unexpected_pattern,
)
BASELINE_RULES = frozenset({"duration_spike", "token_spike", "unexpected_pattern"})
