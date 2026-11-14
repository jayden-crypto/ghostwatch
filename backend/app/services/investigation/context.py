"""What an investigation looks at, loaded once: the execution, its steps, its anomalies, its baseline."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agent, Anomaly, Execution, Step
from app.services.anomaly.baseline import Baseline, load_baseline


@dataclass(frozen=True)
class InvestigationContext:
    execution: Execution
    steps: Sequence[Step]  # sorted by ordinal
    anomalies: Sequence[Anomaly]
    baseline: Baseline
    agent_slug: str


def load_context(session: Session, execution: Execution) -> InvestigationContext:
    return InvestigationContext(
        execution=execution,
        steps=session.scalars(
            select(Step).where(Step.execution_id == execution.id).order_by(Step.ordinal)
        ).all(),
        anomalies=session.scalars(
            select(Anomaly)
            .where(Anomaly.execution_id == execution.id)
            .order_by(Anomaly.detected_at, Anomaly.id)
        ).all(),
        baseline=load_baseline(session, execution),
        agent_slug=session.scalar(select(Agent.slug).where(Agent.id == execution.agent_id)),
    )
