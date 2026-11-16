"""Contract §8 stale_execution: a running execution that stops sending events is timed out by the sweeper."""

import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Anomaly, Event, Execution, Step
from app.services import ingest
from app.sweeper import run_sweeper, sweep_stale_executions
from tests import events as ev
from tests.events import new_step_id, post_events
from tests.factories import T0, make_agent, make_execution

NOW = T0 + timedelta(minutes=10)


def running(session: Session, *, idle_ms: int, timeout_ms: int | None = None) -> Execution:
    """A running execution whose last event arrived `idle_ms` before NOW."""
    config = {} if timeout_ms is None else {"timeout_ms": timeout_ms}
    return make_execution(
        session,
        make_agent(session),
        started_at=T0,
        last_event_at=NOW - timedelta(milliseconds=idle_ms),
        config=config,
    )


def test_a_stale_execution_is_timed_out_through_an_event(
    db_client: TestClient, db_session: Session, auth: dict
) -> None:
    execution = running(db_session, idle_ms=0)
    step = new_step_id()
    post_events(db_client, auth, execution.id, [ev.step_started(1, step, 100), ev.log(2, 200)])
    execution.last_event_at = NOW - timedelta(milliseconds=312450)  # the process died 312 s ago
    db_session.flush()
    last_event_at = execution.last_event_at

    assert ingest.time_out_if_stale(db_session, execution.id, NOW) is True

    assert (execution.status, execution.ended_at, execution.duration_ms) == ("timed_out", NOW, 600000)
    assert execution.error == {
        "type": "TimeoutError",
        "message": "Execution timed out after 600000 ms.",
        "stacktrace": None,
    }
    events = db_session.scalars(
        select(Event).where(Event.execution_id == execution.id).order_by(Event.seq)
    ).all()
    assert [(event.seq, event.type) for event in events] == [
        (1, "step.started"),
        (2, "log"),
        (3, "execution.timed_out"),
    ]
    assert (events[-1].payload, events[-1].timestamp) == ({}, NOW)
    assert (
        db_session.get(Step, step).status == "running"
    )  # what it was doing when it went quiet stays visible

    (anomaly,) = db_session.scalars(select(Anomaly).where(Anomaly.execution_id == execution.id)).all()
    assert (anomaly.type, anomaly.severity, anomaly.rule_id) == (
        "stale_execution",
        "high",
        "stale_execution.v1",
    )
    assert anomaly.title == "No event for 312,450 ms; marked timed out"
    assert "Rule fires after config.timeout_ms = 300,000 ms without an event" in anomaly.explanation
    assert anomaly.evidence[0]["ref_id"] == execution.id
    assert anomaly.evidence[0]["observed"] == {"last_event_at": ev.at(600000 - 312450), "idle_ms": 312450}
    assert last_event_at == NOW - timedelta(milliseconds=312450)

    trace = db_client.get(f"/api/v1/executions/{execution.id}/trace").json()
    assert (trace["execution"]["status"], trace["event_count"], len(trace["anomalies"])) == (
        "timed_out",
        3,
        1,
    )
    # The execution is terminal now: a late step event is refused, a retry of old events is still fine.
    assert post_events(db_client, auth, execution.id, [ev.step_completed(4, step, 700000)]).status_code == 409
    assert post_events(db_client, auth, execution.id, [ev.log(2, 200)]).json()["duplicates"] == 1


@pytest.mark.parametrize(
    ("idle_ms", "timeout_ms", "stale"),
    [
        (299_999, None, False),  # default timeout is 300,000 ms
        (300_000, None, True),
        (999, 1000, False),
        (1000, 1000, True),
        (5000, 1000, True),
        (400_000, 900_000, False),  # a long-running agent with its own timeout
    ],
)
def test_staleness_is_measured_against_the_executions_timeout(
    db_session: Session, idle_ms: int, timeout_ms: int | None, stale: bool
) -> None:
    execution = running(db_session, idle_ms=idle_ms, timeout_ms=timeout_ms)
    assert ingest.time_out_if_stale(db_session, execution.id, NOW) is stale
    assert execution.status == ("timed_out" if stale else "running")
    assert db_session.scalar(select(Anomaly.type).where(Anomaly.execution_id == execution.id)) == (
        "stale_execution" if stale else None
    )


def test_terminal_and_unknown_executions_are_left_alone(db_session: Session) -> None:
    done = running(db_session, idle_ms=10**7)
    done.status = "completed"
    db_session.flush()
    assert ingest.time_out_if_stale(db_session, done.id, NOW) is False
    assert ingest.time_out_if_stale(db_session, "exe_" + "0" * 32, NOW) is False
    assert done.status == "completed"


def test_sweep_times_out_only_the_stale_executions(db_session: Session) -> None:
    stale = [running(db_session, idle_ms=400_000), running(db_session, idle_ms=2000, timeout_ms=1500)]
    alive = [running(db_session, idle_ms=1000), running(db_session, idle_ms=400_000, timeout_ms=900_000)]
    finished = running(db_session, idle_ms=10**7)
    finished.status = "failed"
    db_session.flush()

    assert sweep_stale_executions(db_session, NOW) == 2
    assert [execution.status for execution in stale] == ["timed_out", "timed_out"]
    assert [execution.status for execution in alive] == ["running", "running"]
    assert finished.status == "failed"
    assert sweep_stale_executions(db_session, NOW) == 0  # nothing left to do: a second pass changes nothing
    assert len(db_session.scalars(select(Anomaly)).all()) == 2


def test_an_event_that_arrives_just_before_the_sweep_wins(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sweeper saw a stale execution, but an event landed before it took the row lock."""
    execution = running(db_session, idle_ms=400_000)
    real = ingest.time_out_if_stale

    def event_arrives_first(session: Session, execution_id: str, now: object) -> bool:
        execution.last_event_at = NOW  # ingestion updated it in the meantime
        session.flush()
        return real(session, execution_id, now)

    monkeypatch.setattr(ingest, "time_out_if_stale", event_arrives_first)
    assert sweep_stale_executions(db_session, NOW) == 0
    assert execution.status == "running"


def test_one_failing_execution_does_not_stop_the_sweep(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = running(db_session, idle_ms=400_000), running(db_session, idle_ms=400_000)
    real = ingest.time_out_if_stale
    attempted = []

    def fail_once(session: Session, execution_id: str, now: object) -> bool:
        attempted.append(execution_id)
        if len(attempted) == 1:
            raise RuntimeError("boom")
        return real(session, execution_id, now)

    monkeypatch.setattr(ingest, "time_out_if_stale", fail_once)
    assert sweep_stale_executions(db_session, NOW) == 1
    assert sorted(attempted) == sorted([first.id, second.id])
    assert sorted(execution.status for execution in (first, second)) == ["running", "timed_out"]


def test_the_sweeper_loop_survives_a_failed_pass_and_stops_when_asked() -> None:
    calls = []

    async def scenario() -> None:
        stop = asyncio.Event()

        def sweep() -> None:
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                raise RuntimeError("database is down")
            if len(calls) == 3:
                loop.call_soon_threadsafe(stop.set)

        loop = asyncio.get_running_loop()
        await asyncio.wait_for(run_sweeper(0.01, stop, sweep), timeout=5)

    asyncio.run(scenario())
    assert calls == [1, 2, 3]


def test_the_sweeper_loop_stops_promptly_during_a_long_wait() -> None:
    async def scenario() -> float:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        loop.call_later(0.05, stop.set)
        started = loop.time()
        await run_sweeper(3600, stop, lambda: None)
        return loop.time() - started

    assert asyncio.run(scenario()) < 2
