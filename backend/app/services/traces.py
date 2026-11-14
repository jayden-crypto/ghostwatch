"""Traces: the derived step list with server-computed layout fields, and the raw event log."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.schemas.common import Page
from app.schemas.events import StoredEvent
from app.schemas.traces import Step, Trace
from app.services.anomalies import build_anomalies
from app.services.executions import build_detail, get_execution
from app.timeutil import milliseconds_between


def step_depths(steps: Sequence[models.Step]) -> dict[str, int]:
    """Depth of each step: 0 for roots, parent depth + 1 otherwise.

    Parent ids come from the client. A parent that is not a step of this execution, or a chain that
    loops back on itself, makes the step a root instead of failing the whole trace.
    """
    parents = {step.id: step.parent_step_id for step in steps}
    depths: dict[str, int] = {}
    for step_id in parents:
        chain: list[str] = []
        current: str | None = step_id
        while current in parents and current not in depths and current not in chain:
            chain.append(current)
            current = parents[current]
        # `current` is a step whose depth is known, or the chain ended (root, unknown parent or loop).
        depth = depths[current] + 1 if current in depths else 0
        for ancestor in reversed(chain):
            depths[ancestor] = depth
            depth += 1
    return depths


def get_trace(session: Session, execution_id: str) -> Trace:
    execution = get_execution(session, execution_id)
    steps = session.scalars(
        select(models.Step).where(models.Step.execution_id == execution_id).order_by(models.Step.ordinal)
    ).all()
    anomalies = session.scalars(
        select(models.Anomaly)
        .where(models.Anomaly.execution_id == execution_id)
        .order_by(models.Anomaly.detected_at, models.Anomaly.id)
    ).all()
    event_count = session.scalar(
        select(func.count()).select_from(models.Event).where(models.Event.execution_id == execution_id)
    )
    depths = step_depths(steps)
    return Trace(
        execution=build_detail(session, execution),
        steps=[
            Step(
                id=step.id,
                execution_id=step.execution_id,
                parent_step_id=step.parent_step_id,
                ordinal=step.ordinal,
                depth=depths[step.id],
                name=step.name,
                type=step.type,
                status=step.status,
                started_at=step.started_at,
                ended_at=step.ended_at,
                duration_ms=step.duration_ms,
                # Computed here so the dashboard never does clock arithmetic.
                offset_ms=milliseconds_between(execution.started_at, step.started_at),
                input=step.input,
                output=step.output,
                error=step.error,
                tool_name=step.tool_name,
                model=step.model,
                tokens_input=step.tokens_input,
                tokens_output=step.tokens_output,
                attempt=step.attempt,
                metadata=step.metadata_,
            )
            for step in steps
        ],
        anomalies=build_anomalies(session, anomalies),
        event_count=event_count,
    )


def list_events(session: Session, execution_id: str, *, limit: int, offset: int) -> Page[StoredEvent]:
    """The raw evidence view: events exactly as stored, in seq order."""
    get_execution(session, execution_id)
    total = session.scalar(
        select(func.count()).select_from(models.Event).where(models.Event.execution_id == execution_id)
    )
    events = session.scalars(
        select(models.Event)
        .where(models.Event.execution_id == execution_id)
        .order_by(models.Event.seq)
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        StoredEvent(
            id=event.id,
            seq=event.seq,
            type=event.type,
            timestamp=event.timestamp,
            received_at=event.received_at,
            payload=event.payload,
        )
        for event in events
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)
