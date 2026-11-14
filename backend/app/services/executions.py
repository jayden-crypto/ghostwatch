"""Executions: creation, the filterable list, and the contract's summary and detail shapes."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from app import ids
from app.errors import not_found
from app.models import Agent, Anomaly, Execution, Investigation, Replay
from app.schemas.common import Page
from app.schemas.enums import EXECUTION_STATUSES
from app.schemas.executions import ExecutionConfig, ExecutionCreate, ExecutionDetail, ExecutionSummary
from app.services.payloads import truncate_json
from app.services.query import contains, parse_csv, parse_sort
from app.timeutil import utcnow

# Unknown (NULL) when neither direction was reported; otherwise the sum of what was reported.
TOKENS_TOTAL: ColumnElement[Any] = case(
    (and_(Execution.tokens_input.is_(None), Execution.tokens_output.is_(None)), None),
    else_=func.coalesce(Execution.tokens_input, 0) + func.coalesce(Execution.tokens_output, 0),
)

SORTABLE = {
    "started_at": Execution.started_at,
    "duration_ms": Execution.duration_ms,
    "tokens_total": TOKENS_TOTAL,
    "cost_usd": Execution.cost_usd,
}

CONFIG_DEFAULTS: dict[str, Any] = {"model": None, "params": {}, "expected_steps": None, "timeout_ms": None}


def tokens_total(execution: Execution) -> int | None:
    if execution.tokens_input is None and execution.tokens_output is None:
        return None
    return (execution.tokens_input or 0) + (execution.tokens_output or 0)


def get_execution(session: Session, execution_id: str) -> Execution:
    execution = session.get(Execution, execution_id)
    if execution is None:
        raise not_found("Execution", execution_id)
    return execution


def create_execution(session: Session, body: ExecutionCreate) -> Execution:
    if session.get(Agent, body.agent_id) is None:
        raise not_found("Agent", body.agent_id)
    if body.replay_of is not None and session.get(Execution, body.replay_of) is None:
        raise not_found("Execution", body.replay_of)
    now = utcnow()
    execution = Execution(
        id=ids.new_id(ids.EXECUTION),
        agent_id=body.agent_id,
        status="running",
        started_at=body.started_at or now,
        last_event_at=now,
        input=truncate_json(body.input),
        config=body.stored_config(),
        tags=body.tags,
        replay_of=body.replay_of,
        replay_id=body.replay_id,
        created_at=now,
    )
    session.add(execution)
    session.commit()
    return execution


def list_executions(
    session: Session,
    *,
    agent_id: str | None,
    status: str | None,
    started_after: datetime | None,
    started_before: datetime | None,
    min_duration_ms: int | None,
    max_duration_ms: int | None,
    has_anomaly: bool | None,
    is_replay: bool | None,
    replay_of: str | None,
    q: str | None,
    sort: str,
    limit: int,
    offset: int,
) -> Page[ExecutionSummary]:
    statuses = parse_csv(status, EXECUTION_STATUSES, "status")
    order = parse_sort(sort, SORTABLE)

    conditions: list[ColumnElement[bool]] = []
    if agent_id is not None:
        conditions.append(Execution.agent_id == agent_id)
    if statuses is not None:
        conditions.append(Execution.status.in_(statuses))
    if started_after is not None:
        conditions.append(Execution.started_at >= started_after)
    if started_before is not None:
        conditions.append(Execution.started_at < started_before)
    if min_duration_ms is not None:
        conditions.append(Execution.duration_ms >= min_duration_ms)
    if max_duration_ms is not None:
        conditions.append(Execution.duration_ms <= max_duration_ms)
    if has_anomaly is not None:
        flagged = exists().where(Anomaly.execution_id == Execution.id)
        conditions.append(flagged if has_anomaly else ~flagged)
    if is_replay is not None:
        conditions.append(Execution.replay_of.is_not(None) if is_replay else Execution.replay_of.is_(None))
    if replay_of is not None:
        conditions.append(Execution.replay_of == replay_of)
    if q:
        conditions.append(or_(Execution.id.startswith(q, autoescape=True), contains(Agent.name, q)))

    filtered = select(Execution).join(Agent, Agent.id == Execution.agent_id).where(*conditions)
    total = session.scalar(select(func.count()).select_from(filtered.subquery()))
    executions = session.scalars(filtered.order_by(order, Execution.id).limit(limit).offset(offset)).all()
    return Page(items=build_summaries(session, executions), total=total, limit=limit, offset=offset)


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


def build_detail(session: Session, execution: Execution) -> ExecutionDetail:
    summary = build_summaries(session, [execution])[0]
    replay_ids = session.scalars(
        select(Replay.id)
        .where(Replay.original_execution_id == execution.id)
        .order_by(Replay.requested_at, Replay.id)
    ).all()
    return ExecutionDetail(
        **summary.model_dump(),
        input=execution.input,
        output=execution.output,
        config=ExecutionConfig.model_validate({**CONFIG_DEFAULTS, **execution.config}),
        tokens_input=execution.tokens_input,
        tokens_output=execution.tokens_output,
        tags=execution.tags,
        replay_ids=list(replay_ids),
    )
