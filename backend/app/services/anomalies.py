"""Anomalies: listing, lookup and the contract's Anomaly shape built from stored rows."""

from collections.abc import Sequence
from typing import get_args

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.errors import not_found
from app.schemas.anomalies import Anomaly
from app.schemas.common import Page
from app.schemas.enums import AnomalyStatus, AnomalyType, Severity
from app.services.query import parse_csv, parse_sort

SORTABLE = {"detected_at": models.Anomaly.detected_at}


def get_anomaly(session: Session, anomaly_id: str) -> models.Anomaly:
    anomaly = session.get(models.Anomaly, anomaly_id)
    if anomaly is None:
        raise not_found("Anomaly", anomaly_id)
    return anomaly


def set_status(session: Session, anomaly_id: str, status: AnomalyStatus) -> models.Anomaly:
    """Triage an anomaly. Any status may follow any other, so a resolved anomaly can be reopened."""
    anomaly = get_anomaly(session, anomaly_id)
    anomaly.status = status
    session.commit()
    return anomaly


def list_anomalies(
    session: Session,
    *,
    agent_id: str | None,
    execution_id: str | None,
    type: str | None,
    severity: str | None,
    status: str | None,
    sort: str,
    limit: int,
    offset: int,
) -> Page[Anomaly]:
    types = parse_csv(type, get_args(AnomalyType), "type")
    severities = parse_csv(severity, get_args(Severity), "severity")
    statuses = parse_csv(status, get_args(AnomalyStatus), "status")
    order = parse_sort(sort, SORTABLE)

    conditions = []
    if agent_id is not None:
        conditions.append(models.Anomaly.agent_id == agent_id)
    if execution_id is not None:
        conditions.append(models.Anomaly.execution_id == execution_id)
    if types is not None:
        conditions.append(models.Anomaly.type.in_(types))
    if severities is not None:
        conditions.append(models.Anomaly.severity.in_(severities))
    if statuses is not None:
        conditions.append(models.Anomaly.status.in_(statuses))

    total = session.scalar(select(func.count()).select_from(models.Anomaly).where(*conditions))
    anomalies = session.scalars(
        select(models.Anomaly)
        .where(*conditions)
        .order_by(order, models.Anomaly.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return Page(items=build_anomalies(session, anomalies), total=total, limit=limit, offset=offset)


def build_anomalies(session: Session, anomalies: Sequence[models.Anomaly]) -> list[Anomaly]:
    if not anomalies:
        return []
    agent_ids = {anomaly.agent_id for anomaly in anomalies}
    agent_names = dict(
        session.execute(
            select(models.Agent.id, models.Agent.name).where(models.Agent.id.in_(agent_ids))
        ).all()
    )
    return [
        Anomaly(
            id=anomaly.id,
            type=anomaly.type,
            severity=anomaly.severity,
            status=anomaly.status,
            agent_id=anomaly.agent_id,
            agent_name=agent_names[anomaly.agent_id],
            execution_id=anomaly.execution_id,
            detected_at=anomaly.detected_at,
            rule_id=anomaly.rule_id,
            title=anomaly.title,
            explanation=anomaly.explanation,
            evidence=anomaly.evidence,
        )
        for anomaly in anomalies
    ]
