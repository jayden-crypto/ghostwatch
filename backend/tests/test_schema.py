"""The Alembic migration creates the schema in PROJECT_PLAN.md §3, and the ORM models agree with it."""

import re
from decimal import Decimal

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import func, inspect, select, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.types import DateTime, Numeric

from app import ids
from app.db import get_engine
from app.models import Agent, Anomaly, Base, Event, Execution, Step
from tests.conftest import alembic_config
from tests.factories import T0, make_agent, make_execution

TABLES = {"agents", "executions", "events", "steps", "anomalies", "investigations", "replays"}
TIMESTAMP_COLUMNS = {
    "agents": {"created_at"},
    "executions": {"started_at", "ended_at", "last_event_at", "created_at"},
    "events": {"timestamp", "received_at"},
    "steps": {"started_at", "ended_at"},
    "anomalies": {"detected_at"},
    "investigations": {"created_at", "completed_at"},
    "replays": {"requested_at", "claimed_at", "completed_at"},
}


def assert_rejected(session: Session, row: Base) -> None:
    """The row violates a constraint; the savepoint keeps the test's transaction usable."""
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(row)
        session.flush()


def make_step(execution: Execution, ordinal: int) -> Step:
    return Step(
        id=ids.new_id(ids.STEP),
        execution_id=execution.id,
        ordinal=ordinal,
        name="plan",
        type="reasoning",
        status="running",
        started_at=T0,
    )


def make_event(execution_id: str, seq: int) -> Event:
    return Event(
        id=ids.new_id(ids.EVENT),
        execution_id=execution_id,
        seq=seq,
        type="log",
        timestamp=T0,
        received_at=T0,
        payload={"level": "info", "message": "hello", "step_id": None},
    )


def make_anomaly(agent: Agent, execution_id: str | None, type_: str = "ghost_completion") -> Anomaly:
    return Anomaly(
        id=ids.new_id(ids.ANOMALY),
        agent_id=agent.id,
        execution_id=execution_id,
        type=type_,
        severity="critical",
        rule_id=f"{type_}.v1",
        title="t",
        explanation="e",
        evidence=[],
        detected_at=T0,
    )


def test_migration_creates_every_table(migrated_database: None) -> None:
    assert set(inspect(get_engine()).get_table_names()) == TABLES | {"alembic_version"}


def test_models_match_the_migrated_schema(migrated_database: None) -> None:
    with get_engine().connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []


def test_column_types(migrated_database: None) -> None:
    inspector = inspect(get_engine())
    for table, names in TIMESTAMP_COLUMNS.items():
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        for name in names:
            assert isinstance(columns[name]["type"], DateTime) and columns[name]["type"].timezone, (
                table,
                name,
            )
        assert columns["id"]["type"].__class__.__name__ == "TEXT", table

    executions = {column["name"]: column for column in inspector.get_columns("executions")}
    for name in ("input", "output", "config", "error"):
        assert isinstance(executions[name]["type"], JSONB), name
    assert isinstance(executions["tags"]["type"], ARRAY)
    cost = executions["cost_usd"]["type"]
    assert isinstance(cost, Numeric) and (cost.precision, cost.scale) == (12, 6)
    assert isinstance(inspector.get_columns("events")[-1]["type"], JSONB)


def test_indexes_exist(migrated_database: None) -> None:
    inspector = inspect(get_engine())
    executions = {index["name"]: index for index in inspector.get_indexes("executions")}
    assert {"ix_executions_agent_id_started_at", "ix_executions_status", "ix_executions_replay_of"} <= set(
        executions
    )
    with get_engine().connect() as connection:
        definition = connection.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_executions_agent_id_started_at'")
        )
    assert "(agent_id, started_at DESC)" in definition
    steps = {index["name"] for index in inspector.get_indexes("steps")}
    assert {"ix_steps_execution_id", "ix_steps_tool_name"} <= steps


def test_server_defaults(db_session: Session) -> None:
    agent_id, execution_id = ids.new_id(ids.AGENT), ids.new_id(ids.EXECUTION)
    db_session.execute(
        text("INSERT INTO agents (id, slug, name, created_at) VALUES (:id, 'raw-agent', 'Raw', now())"),
        {"id": agent_id},
    )
    db_session.execute(
        text(
            "INSERT INTO executions (id, agent_id, status, started_at, last_event_at, created_at) "
            "VALUES (:id, :agent_id, 'running', now(), now(), now())"
        ),
        {"id": execution_id, "agent_id": agent_id},
    )
    agent = db_session.get(Agent, agent_id)
    execution = db_session.get(Execution, execution_id)
    assert agent.metadata_ == {}
    assert (execution.config, execution.tags, execution.step_count) == ({}, [], 0)
    assert execution.input is None and execution.cost_usd is None


def test_json_null_is_stored_as_sql_null(db_session: Session) -> None:
    execution = make_execution(db_session, make_agent(db_session), input=None, output=None)
    stored = db_session.execute(
        text("SELECT input IS NULL, output IS NULL FROM executions WHERE id = :id"), {"id": execution.id}
    ).one()
    assert tuple(stored) == (True, True)


def test_values_round_trip(db_session: Session) -> None:
    agent = make_agent(db_session, metadata_={"team": "search"})
    execution = make_execution(
        db_session, agent, input={"q": [1, "two", None]}, tags=["demo", "seed"], cost_usd=Decimal("0.012345")
    )
    db_session.expire_all()
    reloaded = db_session.get(Execution, execution.id)
    assert reloaded.input == {"q": [1, "two", None]}
    assert reloaded.tags == ["demo", "seed"]
    assert reloaded.cost_usd == Decimal("0.012345")
    assert reloaded.started_at == T0 and reloaded.started_at.utcoffset().total_seconds() == 0
    assert db_session.get(Agent, agent.id).metadata_ == {"team": "search"}


def test_agent_slug_is_unique(db_session: Session) -> None:
    make_agent(db_session, slug="research-assistant")
    assert_rejected(
        db_session, Agent(id=ids.new_id(ids.AGENT), slug="research-assistant", name="Other", created_at=T0)
    )


def test_execution_status_is_checked(db_session: Session) -> None:
    agent = make_agent(db_session)
    for status in ("running", "completed", "failed", "timed_out"):
        make_execution(db_session, agent, status=status)
    assert_rejected(
        db_session,
        Execution(
            id=ids.new_id(ids.EXECUTION),
            agent_id=agent.id,
            status="cancelled",
            started_at=T0,
            last_event_at=T0,
            created_at=T0,
        ),
    )


def test_foreign_keys_are_enforced(db_session: Session) -> None:
    assert_rejected(
        db_session,
        Execution(
            id=ids.new_id(ids.EXECUTION),
            agent_id="agt_" + "0" * 32,
            status="running",
            started_at=T0,
            last_event_at=T0,
            created_at=T0,
        ),
    )
    assert_rejected(db_session, make_event("exe_" + "0" * 32, 1))


def test_event_seq_is_unique_per_execution(db_session: Session) -> None:
    agent = make_agent(db_session)
    first, second = make_execution(db_session, agent), make_execution(db_session, agent)
    db_session.add_all([make_event(first.id, 1), make_event(first.id, 2), make_event(second.id, 1)])
    db_session.flush()
    assert_rejected(db_session, make_event(first.id, 1))
    assert db_session.scalar(select(func.count()).select_from(Event)) == 3


def test_step_ordinal_is_unique_per_execution(db_session: Session) -> None:
    execution = make_execution(db_session, make_agent(db_session))
    db_session.add_all([make_step(execution, 1), make_step(execution, 2)])
    db_session.flush()
    assert_rejected(db_session, make_step(execution, 2))


def test_one_anomaly_of_each_type_per_execution(db_session: Session) -> None:
    agent = make_agent(db_session)
    execution = make_execution(db_session, agent)
    db_session.add_all(
        [make_anomaly(agent, execution.id), make_anomaly(agent, execution.id, "duration_spike")]
    )
    db_session.flush()
    assert_rejected(db_session, make_anomaly(agent, execution.id))


def test_committed_rows_do_not_outlive_a_test_part_1(db_session: Session) -> None:
    make_agent(db_session, slug="leak-check")
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(Agent)) == 1


def test_committed_rows_do_not_outlive_a_test_part_2(db_session: Session) -> None:
    assert db_session.scalar(select(func.count()).select_from(Agent)) == 0


def test_downgrade_and_upgrade_round_trip(migrated_database: None) -> None:
    config = alembic_config()
    command.downgrade(config, "base")
    assert set(inspect(get_engine()).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    assert set(inspect(get_engine()).get_table_names()) == TABLES | {"alembic_version"}


@pytest.mark.parametrize(
    "prefix", [ids.AGENT, ids.EXECUTION, ids.STEP, ids.EVENT, ids.ANOMALY, ids.INVESTIGATION, ids.REPLAY]
)
def test_ids_are_a_prefix_and_32_lowercase_hex(prefix: str) -> None:
    generated = {ids.new_id(prefix) for _ in range(200)}
    assert len(generated) == 200
    assert all(re.fullmatch(rf"{prefix}_[0-9a-f]{{32}}", value) for value in generated)


def test_id_prefixes_match_the_contract() -> None:
    prefixes = {ids.AGENT, ids.EXECUTION, ids.STEP, ids.EVENT, ids.ANOMALY, ids.INVESTIGATION, ids.REPLAY}
    assert prefixes == {"agt", "exe", "stp", "evt", "anm", "inv", "rpl"}
