"""Runs the rules for one terminal execution and stores what they raise."""

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import ids
from app.models import Agent, Anomaly, Execution, Step
from app.services.anomaly import thresholds
from app.services.anomaly.baseline import load_baseline, load_recent_runs
from app.services.anomaly.rules import BASELINE_RULES, RULES, RuleInput, StaleInfo
from app.timeutil import utcnow

logger = logging.getLogger("ghostwatch")


def evaluate(session: Session, execution: Execution, *, stale: StaleInfo | None = None) -> list[Anomaly]:
    """Evaluate every rule and return the anomalies that were newly created.

    Running it again for the same execution creates nothing: UNIQUE(execution_id, type) with
    ON CONFLICT DO NOTHING makes the engine idempotent.
    """
    steps = session.scalars(
        select(Step).where(Step.execution_id == execution.id).order_by(Step.ordinal)
    ).all()
    baseline = load_baseline(session, execution)
    rule_input = RuleInput(
        execution=execution,
        steps=steps,
        baseline=baseline,
        recent_runs=load_recent_runs(session, execution),
        agent_slug=session.scalar(select(Agent.slug).where(Agent.id == execution.agent_id)),
        stale=stale,
    )
    if not baseline.is_sufficient:
        logger.info(
            "Anomaly rules %s skipped for %s: %d baseline run(s), %d needed",
            sorted(BASELINE_RULES),
            execution.id,
            baseline.runs,
            thresholds.MIN_BASELINE_RUNS,
        )

    created: list[Anomaly] = []
    for rule in RULES:
        draft = rule(rule_input)
        if draft is None:
            continue
        anomaly_id = session.scalar(
            insert(Anomaly)
            .values(
                id=ids.new_id(ids.ANOMALY),
                agent_id=execution.agent_id,
                execution_id=execution.id,
                type=draft.type,
                severity=draft.severity,
                status="open",
                rule_id=draft.rule_id,
                title=draft.title,
                explanation=draft.explanation,
                evidence=draft.evidence,
                detected_at=utcnow(),
            )
            .on_conflict_do_nothing(index_elements=[Anomaly.execution_id, Anomaly.type])
            .returning(Anomaly.id)
        )
        if anomaly_id is not None:
            created.append(session.get(Anomaly, anomaly_id))
    return created
