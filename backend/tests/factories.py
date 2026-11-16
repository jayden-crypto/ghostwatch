"""Minimal valid rows for tests that need existing data."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app import ids
from app.models import Agent, Anomaly, Execution, Investigation, Replay, Step

T0 = datetime(2026, 11, 14, 10, 0, 0, tzinfo=UTC)


def make_agent(session: Session, **overrides: Any) -> Agent:
    agent_id = ids.new_id(ids.AGENT)
    values: dict[str, Any] = {
        "id": agent_id,
        "slug": f"agent-{agent_id[-8:]}",
        "name": "Test Agent",
        "created_at": T0,
    }
    values.update(overrides)
    agent = Agent(**values)
    session.add(agent)
    session.flush()
    return agent


def make_execution(session: Session, agent: Agent, **overrides: Any) -> Execution:
    values: dict[str, Any] = {
        "id": ids.new_id(ids.EXECUTION),
        "agent_id": agent.id,
        "status": "running",
        "started_at": T0,
        "last_event_at": T0,
        "created_at": T0,
    }
    values.update(overrides)
    execution = Execution(**values)
    session.add(execution)
    session.flush()
    return execution


def make_anomaly(session: Session, execution: Execution, **overrides: Any) -> Anomaly:
    values: dict[str, Any] = {
        "id": ids.new_id(ids.ANOMALY),
        "agent_id": execution.agent_id,
        "execution_id": execution.id,
        "type": "excessive_retries",
        "severity": "medium",
        "status": "open",
        "rule_id": "excessive_retries.v1",
        "title": "Test anomaly",
        "explanation": "Created by a test.",
        "evidence": [
            {
                "kind": "execution",
                "label": "Execution under test",
                "ref_id": execution.id,
                "field": "status",
                "observed": execution.status,
                "expected": None,
                "excerpt": None,
            }
        ],
        "detected_at": T0,
    }
    values.update(overrides)
    anomaly = Anomaly(**values)
    session.add(anomaly)
    session.flush()
    return anomaly


def make_investigation(session: Session, execution: Execution, **overrides: Any) -> Investigation:
    values: dict[str, Any] = {
        "id": ids.new_id(ids.INVESTIGATION),
        "execution_id": execution.id,
        "status": "queued",
        "trigger": "manual",
        "provider": "rule_based",
        "created_at": T0,
    }
    values.update(overrides)
    investigation = Investigation(**values)
    session.add(investigation)
    session.flush()
    return investigation


def make_replay(session: Session, original: Execution, **overrides: Any) -> Replay:
    values: dict[str, Any] = {
        "id": ids.new_id(ids.REPLAY),
        "original_execution_id": original.id,
        "mode": "sandbox",
        "status": "pending",
        "requested_at": T0,
    }
    values.update(overrides)
    replay = Replay(**values)
    session.add(replay)
    session.flush()
    return replay


def make_step(session: Session, execution: Execution, ordinal: int, **overrides: Any) -> Step:
    values: dict[str, Any] = {
        "id": ids.new_id(ids.STEP),
        "execution_id": execution.id,
        "ordinal": ordinal,
        "name": "work",
        "type": "custom",
        "status": "completed",
        "started_at": execution.started_at,
    }
    values.update(overrides)
    step = Step(**values)
    session.add(step)
    session.flush()
    return step
