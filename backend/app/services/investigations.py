"""Investigations as the API sees them: requesting one, finding the latest, listing them."""

from typing import get_args

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.errors import ApiError
from app.schemas.common import Page
from app.schemas.enums import InvestigationStatus
from app.schemas.investigations import Investigation
from app.services.executions import get_execution
from app.services.investigation import engine
from app.services.query import parse_csv, parse_sort

SORTABLE = {"created_at": models.Investigation.created_at}
IN_FLIGHT = ("queued", "running")


def to_schema(investigation: models.Investigation) -> Investigation:
    """The contract shape. `llm_raw_response` is deliberately not part of it."""
    return Investigation(
        id=investigation.id,
        execution_id=investigation.execution_id,
        status=investigation.status,
        trigger=investigation.trigger,
        provider=investigation.provider,
        model=investigation.model,
        created_at=investigation.created_at,
        completed_at=investigation.completed_at,
        error=investigation.error,
        report=investigation.report,
    )


def _latest(session: Session, execution_id: str) -> models.Investigation | None:
    return session.scalars(
        select(models.Investigation)
        .where(models.Investigation.execution_id == execution_id)
        .order_by(models.Investigation.created_at.desc(), models.Investigation.id.desc())
        .limit(1)
    ).first()


def get_latest(session: Session, execution_id: str) -> models.Investigation:
    investigation = _latest(session, execution_id)
    if investigation is None:
        get_execution(session, execution_id)  # a 404 that names the execution if that is what is missing
        raise ApiError(404, "not_found", f"Execution {execution_id} has not been investigated.")
    return investigation


def request(session: Session, execution_id: str, *, force: bool) -> tuple[models.Investigation, bool]:
    """Queue a manual investigation unless one already answers the request.

    Returns the investigation and whether it was newly queued. An investigation that is already
    queued or running is returned as it is. A completed one is returned unless `force` is set.
    """
    execution = get_execution(session, execution_id)
    if execution.status == "running":
        raise ApiError(
            409,
            "conflict",
            f"Execution {execution_id} is still running; it can be investigated once it has ended.",
        )
    latest = _latest(session, execution_id)
    if latest is not None and (latest.status in IN_FLIGHT or (latest.status == "completed" and not force)):
        return latest, False
    investigation = engine.queue(session, execution, "manual")
    session.commit()
    return investigation, True


def list_investigations(
    session: Session, *, status: str | None, agent_id: str | None, sort: str, limit: int, offset: int
) -> Page[Investigation]:
    statuses = parse_csv(status, get_args(InvestigationStatus), "status")
    order = parse_sort(sort, SORTABLE)
    conditions = []
    if statuses is not None:
        conditions.append(models.Investigation.status.in_(statuses))
    if agent_id is not None:
        conditions.append(models.Execution.agent_id == agent_id)
    filtered = (
        select(models.Investigation)
        .join(models.Execution, models.Execution.id == models.Investigation.execution_id)
        .where(*conditions)
    )
    total = session.scalar(select(func.count()).select_from(filtered.subquery()))
    rows = session.scalars(
        filtered.order_by(order, models.Investigation.id).limit(limit).offset(offset)
    ).all()
    return Page(items=[to_schema(row) for row in rows], total=total, limit=limit, offset=offset)
