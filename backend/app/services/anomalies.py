"""Anomalies: building the contract's Anomaly from stored rows."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.schemas.anomalies import Anomaly


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
