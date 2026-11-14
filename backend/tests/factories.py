"""Minimal valid rows for tests that need existing data."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app import ids
from app.models import Agent, Execution

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
