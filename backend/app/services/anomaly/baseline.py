"""What an agent's recent history looks like: the baseline and the recent runs the rules compare against."""

import math
import statistics
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Execution, Step
from app.schemas.enums import TERMINAL_STATUSES
from app.services.anomaly import thresholds
from app.services.executions import tokens_total


def percentile_95(values: list[int]) -> int:
    """Nearest-rank 95th percentile: the smallest value with at least 95 % of the values at or below it."""
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


@dataclass(frozen=True)
class Baseline:
    """The agent's last completed, non-replay executions before the one being evaluated."""

    durations_ms: list[int] = field(default_factory=list)
    token_totals: list[int] = field(default_factory=list)  # only runs that reported tokens
    step_counts: list[int] = field(default_factory=list)
    tool_names: frozenset[str] = frozenset()

    @property
    def runs(self) -> int:
        return len(self.durations_ms)

    @property
    def is_sufficient(self) -> bool:
        return self.runs >= thresholds.MIN_BASELINE_RUNS

    @property
    def has_token_baseline(self) -> bool:
        return len(self.token_totals) >= thresholds.MIN_BASELINE_RUNS

    @property
    def duration_median(self) -> float:
        return statistics.median(self.durations_ms)

    @property
    def duration_p95(self) -> int:
        return percentile_95(self.durations_ms)

    @property
    def token_median(self) -> float:
        return statistics.median(self.token_totals)

    @property
    def token_p95(self) -> int:
        return percentile_95(self.token_totals)

    @property
    def max_step_count(self) -> int:
        return max(self.step_counts)


@dataclass(frozen=True)
class RecentRun:
    """One of the agent's recent terminal executions, newest first, including the one being evaluated."""

    execution_id: str
    status: str
    failed_tools: frozenset[str]


def _history(execution: Execution):
    """Non-replay executions of the same agent that started no later than this one."""
    return select(Execution).where(
        Execution.agent_id == execution.agent_id,
        Execution.replay_of.is_(None),
        Execution.started_at <= execution.started_at,
    )


def load_baseline(session: Session, execution: Execution) -> Baseline:
    runs = session.scalars(
        _history(execution)
        .where(Execution.status == "completed", Execution.id != execution.id)
        .order_by(Execution.started_at.desc(), Execution.id.desc())
        .limit(thresholds.BASELINE_SIZE)
    ).all()
    tool_names = session.scalars(
        select(Step.tool_name)
        .where(Step.execution_id.in_([run.id for run in runs]), Step.tool_name.is_not(None))
        .distinct()
    ).all()
    return Baseline(
        durations_ms=[run.duration_ms for run in runs if run.duration_ms is not None],
        token_totals=[total for run in runs if (total := tokens_total(run)) is not None],
        step_counts=[run.step_count for run in runs],
        tool_names=frozenset(tool_names),
    )


def load_recent_runs(session: Session, execution: Execution) -> list[RecentRun]:
    """The agent's last terminal, non-replay executions up to and including this one, newest first.

    The execution being evaluated is always first, even if it is a replay, so agent-level rules can
    tell whether it is part of the pattern.
    """
    others = session.scalars(
        _history(execution)
        .where(Execution.status.in_(TERMINAL_STATUSES), Execution.id != execution.id)
        .order_by(Execution.started_at.desc(), Execution.id.desc())
        .limit(thresholds.TIMEOUTS_WINDOW - 1)
    ).all()
    runs = [execution, *others]
    failed: dict[str, set[str]] = {run.id: set() for run in runs}
    for execution_id, tool_name in session.execute(
        select(Step.execution_id, Step.tool_name).where(
            Step.execution_id.in_(list(failed)), Step.status == "failed", Step.tool_name.is_not(None)
        )
    ):
        failed[execution_id].add(tool_name)
    return [RecentRun(run.id, run.status, frozenset(failed[run.id])) for run in runs]
