"""Executions: building the contract's ExecutionSummary from stored rows."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Agent, Anomaly, Execution, Investigation
from app.schemas.executions import ExecutionSummary


def tokens_total(execution: Execution) -> int | None:
    """Sum of reported tokens; None (unknown) when neither direction was reported."""
    if execution.tokens_input is None and execution.tokens_output is None:
        return None
    return (execution.tokens_input or 0) + (execution.tokens_output or 0)


def build_summaries(session: Session, executions: Sequence[Execution]) -> list[ExecutionSummary]:
    if not executions:
        return []
    execution_ids = [execution.id for execution in executions]
    agent_ids = {execution.agent_id for execution in executions}
    agent_names = dict(session.execute(select(Agent.id, Agent.name).where(Agent.id.in_(agent_ids))).all())
    anomaly_counts = dict(
        session.execute(
            select(Anomaly.execution_id, func.count())
            .where(Anomaly.execution_id.in_(execution_ids))
            .group_by(Anomaly.execution_id)
        ).all()
    )
    investigated = set(
        session.scalars(
            select(Investigation.execution_id).where(Investigation.execution_id.in_(execution_ids)).distinct()
        )
    )
    return [
        ExecutionSummary(
            id=execution.id,
            agent_id=execution.agent_id,
            agent_name=agent_names[execution.agent_id],
            status=execution.status,
            started_at=execution.started_at,
            ended_at=execution.ended_at,
            duration_ms=execution.duration_ms,
            step_count=execution.step_count,
            tokens_total=tokens_total(execution),
            cost_usd=None if execution.cost_usd is None else float(execution.cost_usd),
            anomaly_count=anomaly_counts.get(execution.id, 0),
            has_investigation=execution.id in investigated,
            replay_of=execution.replay_of,
            error=execution.error,
        )
        for execution in executions
    ]
