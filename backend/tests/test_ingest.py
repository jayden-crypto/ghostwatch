"""Contract §5: event ingestion, and the steps, status and totals derived from it."""

import json
import threading
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Agent, Event, Execution, Step
from app.schemas.events import IngestRequest
from app.services.ingest import ingest_events
from tests import events as ev
from tests.events import new_step_id, post_events
from tests.factories import T0, make_agent, make_execution


@pytest.fixture
def execution(db_session: Session) -> Execution:
    return make_execution(db_session, make_agent(db_session))


def steps_of(session: Session, execution: Execution) -> list[Step]:
    return list(session.scalars(select(Step).where(Step.execution_id == execution.id).order_by(Step.ordinal)))


def event_count(session: Session, execution: Execution) -> int:
    return session.scalar(select(func.count()).select_from(Event).where(Event.execution_id == execution.id))


def assert_nothing_stored(session: Session, execution: Execution) -> None:
    assert event_count(session, execution) == 0
    assert steps_of(session, execution) == []
    assert (execution.status, execution.step_count, execution.last_event_at) == ("running", 0, T0)


def test_a_full_run_derives_steps_status_and_totals(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    plan, search_1, search_2, parse, child = (new_step_id() for _ in range(5))
    response = post_events(
        db_client,
        auth,
        execution.id,
        [
            ev.step_started(1, plan, 0, input={"question": "q"}),
            ev.step_completed(2, plan, 120, output={"queries": ["a"]}),
            ev.step_started(
                3, search_1, 130, name="web_search", step_type="tool_call", tool_name="web_search"
            ),
            ev.step_failed(
                4, search_1, 430, error={"type": "HTTPError", "message": "429"}, output={"status": 429}
            ),
            ev.step_started(
                5, search_2, 500, name="web_search", step_type="tool_call", tool_name="web_search", attempt=2
            ),
            ev.step_completed(6, search_2, 900, output={"results": [1, 2]}),
            ev.step_started(7, parse, 910, name="summarize", step_type="llm_call", model="claude-fable-5-2"),
            ev.step_started(8, child, 915, name="format", step_type="custom", parent_step_id=parse),
            ev.step_completed(9, child, 930),
            ev.step_completed(10, parse, 1910, output="done", tokens_input=1200, tokens_output=300),
            ev.log(11, 1911, message="wrapping up", step_id=parse),
            ev.execution_completed(12, 2000, output={"answer": 42}),
        ],
    )
    assert response.status_code == 202, response.text
    assert response.json() == {"accepted": 12, "duplicates": 0, "execution_status": "completed"}

    steps = steps_of(db_session, execution)
    assert [step.ordinal for step in steps] == [1, 2, 3, 4, 5]
    assert [step.id for step in steps] == [plan, search_1, search_2, parse, child]
    assert [step.status for step in steps] == ["completed", "failed", "completed", "completed", "completed"]
    assert [step.duration_ms for step in steps] == [120, 300, 400, 1000, 15]
    assert [step.attempt for step in steps] == [1, 1, 2, 1, 1]
    assert [step.parent_step_id for step in steps] == [None, None, None, None, parse]
    assert [step.type for step in steps] == ["reasoning", "tool_call", "tool_call", "llm_call", "custom"]
    assert (steps[1].tool_name, steps[3].model) == ("web_search", "claude-fable-5-2")
    assert steps[0].input == {"question": "q"} and steps[0].output == {"queries": ["a"]}
    assert steps[1].error == {"type": "HTTPError", "message": "429", "stacktrace": None}
    assert steps[1].output == {"status": 429}
    assert steps[0].started_at == T0 and steps[0].ended_at == T0 + timedelta(milliseconds=120)
    assert (steps[3].tokens_input, steps[3].tokens_output) == (1200, 300)

    detail = db_client.get(f"/api/v1/executions/{execution.id}").json()
    assert (detail["status"], detail["step_count"], detail["duration_ms"]) == ("completed", 5, 2000)
    assert detail["ended_at"] == ev.at(2000)
    assert detail["output"] == {"answer": 42}
    assert (detail["tokens_input"], detail["tokens_output"], detail["tokens_total"]) == (1200, 300, 1500)
    assert (detail["cost_usd"], detail["error"]) == (None, None)
    assert event_count(db_session, execution) == 12
    assert execution.last_event_at > T0


def test_reposting_the_same_batch_changes_nothing(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    step = new_step_id()
    batch = [ev.step_started(1, step), ev.step_completed(2, step, 50), ev.log(3, 60)]
    assert post_events(db_client, auth, execution.id, batch).json() == {
        "accepted": 3,
        "duplicates": 0,
        "execution_status": "running",
    }
    last_event_at = execution.last_event_at

    again = post_events(db_client, auth, execution.id, batch)
    assert again.status_code == 202
    assert again.json() == {"accepted": 0, "duplicates": 3, "execution_status": "running"}
    assert event_count(db_session, execution) == 3
    assert len(steps_of(db_session, execution)) == 1
    assert (execution.step_count, execution.last_event_at) == (1, last_event_at)


def test_duplicates_within_and_across_batches(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    first = post_events(
        db_client, auth, execution.id, [ev.log(1), ev.log(2), ev.log(2, message="again"), ev.log(3)]
    )
    assert first.json() == {"accepted": 3, "duplicates": 1, "execution_status": "running"}

    overlap = post_events(db_client, auth, execution.id, [ev.log(2), ev.log(3), ev.log(4)])
    assert overlap.json() == {"accepted": 1, "duplicates": 2, "execution_status": "running"}

    stored = db_session.execute(
        select(Event.seq, Event.payload["message"].astext)
        .where(Event.execution_id == execution.id)
        .order_by(Event.seq)
    ).all()
    assert [tuple(row) for row in stored] == [(1, "hello"), (2, "hello"), (3, "hello"), (4, "hello")]


def test_a_batch_is_processed_in_seq_order(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    first, second = new_step_id(), new_step_id()
    response = post_events(
        db_client,
        auth,
        execution.id,
        [
            ev.execution_completed(5, 300),
            ev.step_completed(4, second, 250),
            ev.step_completed(2, first, 100),
            ev.step_started(3, second, 150, name="second"),
            ev.step_started(1, first, 0, name="first"),
        ],
    )
    assert response.json() == {"accepted": 5, "duplicates": 0, "execution_status": "completed"}
    assert [(step.ordinal, step.name, step.status) for step in steps_of(db_session, execution)] == [
        (1, "first", "completed"),
        (2, "second", "completed"),
    ]


def test_steps_span_batches_and_ordinals_continue(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    first, second = new_step_id(), new_step_id()
    started = post_events(db_client, auth, execution.id, [ev.step_started(1, first, 0)])
    assert started.json()["execution_status"] == "running"
    assert steps_of(db_session, execution)[0].status == "running"
    assert steps_of(db_session, execution)[0].ended_at is None

    post_events(
        db_client, auth, execution.id, [ev.step_completed(2, first, 75), ev.step_started(3, second, 80)]
    )
    steps = steps_of(db_session, execution)
    assert [(step.ordinal, step.status, step.duration_ms) for step in steps] == [
        (1, "completed", 75),
        (2, "running", None),
    ]
    assert execution.step_count == 2


def test_unknown_step_rejects_the_whole_batch(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    response = post_events(
        db_client,
        auth,
        execution.id,
        [ev.step_started(1, new_step_id()), ev.log(2), ev.step_completed(3, new_step_id())],
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["body", "events", 2, "payload", "step_id"]
    assert "never started" in error["details"][0]["msg"]
    assert_nothing_stored(db_session, execution)


def test_step_ids_cannot_be_reused_or_borrowed(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    other = make_execution(db_session, make_agent(db_session))
    step = new_step_id()
    assert post_events(db_client, auth, other.id, [ev.step_started(1, step)]).status_code == 202

    # Another execution's step can be neither finished nor started again from here.
    assert post_events(db_client, auth, execution.id, [ev.step_completed(1, step)]).status_code == 422
    assert post_events(db_client, auth, execution.id, [ev.step_started(1, step)]).status_code == 422
    # Nor can the owning execution start it twice or end it twice.
    assert post_events(db_client, auth, other.id, [ev.step_started(2, step)]).status_code == 422
    assert post_events(db_client, auth, other.id, [ev.step_completed(2, step, 10)]).status_code == 202
    twice = post_events(db_client, auth, other.id, [ev.step_failed(3, step, 20)])
    assert twice.status_code == 422
    assert "already completed" in twice.json()["error"]["details"][0]["msg"]

    assert_nothing_stored(db_session, execution)
    assert steps_of(db_session, other)[0].status == "completed"
    assert event_count(db_session, other) == 2


def test_after_a_terminal_event_only_logs_and_retries_are_accepted(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    step = new_step_id()
    final_batch = [ev.step_started(1, step), ev.step_completed(2, step, 10), ev.execution_failed(3, 20)]
    assert post_events(db_client, auth, execution.id, final_batch).json()["execution_status"] == "failed"

    late = post_events(db_client, auth, execution.id, [ev.log(4, 30), ev.step_started(5, new_step_id(), 40)])
    assert late.status_code == 409
    error = late.json()["error"]
    assert error["code"] == "execution_already_terminal"
    assert error["details"] == {"execution_status": "failed", "rejected_seq": 5}
    assert event_count(db_session, execution) == 3  # the log in the rejected batch was not stored either

    second_terminal = post_events(db_client, auth, execution.id, [ev.execution_completed(4, 30)])
    assert second_terminal.status_code == 409

    # An SDK retry of the final batch is a duplicate, not a conflict.
    retry = post_events(db_client, auth, execution.id, final_batch)
    assert retry.status_code == 202
    assert retry.json() == {"accepted": 0, "duplicates": 3, "execution_status": "failed"}

    logs = post_events(db_client, auth, execution.id, [ev.log(4, 30, message="flushed late")])
    assert logs.json() == {"accepted": 1, "duplicates": 0, "execution_status": "failed"}
    assert event_count(db_session, execution) == 4
    assert (execution.status, execution.duration_ms) == ("failed", 20)


def test_events_after_the_terminal_event_in_one_batch_are_rejected(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    response = post_events(
        db_client, auth, execution.id, [ev.execution_completed(1, 10), ev.step_started(2, new_step_id(), 20)]
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"execution_status": "completed", "rejected_seq": 2}
    assert_nothing_stored(db_session, execution)


def test_failed_execution_records_the_error(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    response = post_events(db_client, auth, execution.id, [ev.execution_failed(1, 1500)])
    assert response.json()["execution_status"] == "failed"
    detail = db_client.get(f"/api/v1/executions/{execution.id}").json()
    assert detail["error"] == ev.KEY_ERROR
    assert (detail["status"], detail["duration_ms"], detail["output"]) == ("failed", 1500, None)


def test_timed_out_execution_gets_a_templated_error(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    response = post_events(db_client, auth, execution.id, [ev.execution_timed_out(1, 300000)])
    assert response.json()["execution_status"] == "timed_out"
    detail = db_client.get(f"/api/v1/executions/{execution.id}").json()
    assert detail["error"] == {
        "type": "TimeoutError",
        "message": "Execution timed out after 300000 ms.",
        "stacktrace": None,
    }


def test_completion_leaves_running_steps_running(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    """A step that never finished is evidence of a ghost completion; ingestion must not tidy it away."""
    post_events(
        db_client, auth, execution.id, [ev.step_started(1, new_step_id()), ev.execution_completed(2, 100)]
    )
    step = steps_of(db_session, execution)[0]
    assert (execution.status, step.status, step.ended_at, step.duration_ms) == (
        "completed",
        "running",
        None,
        None,
    )


def test_token_totals_are_unknown_when_no_step_reports_tokens(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    step = new_step_id()
    post_events(
        db_client,
        auth,
        execution.id,
        [ev.step_started(1, step), ev.step_completed(2, step, 10), ev.execution_completed(3, 20)],
    )
    detail = db_client.get(f"/api/v1/executions/{execution.id}").json()
    assert (detail["tokens_input"], detail["tokens_output"], detail["tokens_total"]) == (None, None, None)


def test_token_totals_sum_only_what_was_reported(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    a, b, c = new_step_id(), new_step_id(), new_step_id()
    post_events(
        db_client,
        auth,
        execution.id,
        [
            ev.step_started(1, a),
            ev.step_completed(2, a, 10, tokens_input=100, tokens_output=20),
            ev.step_started(3, b, 20),
            ev.step_completed(4, b, 30, tokens_input=50),
            ev.step_started(5, c, 40),
            ev.step_completed(6, c, 50),
            ev.execution_completed(7, 60),
        ],
    )
    detail = db_client.get(f"/api/v1/executions/{execution.id}").json()
    assert (detail["tokens_input"], detail["tokens_output"], detail["tokens_total"]) == (150, 20, 170)


def test_oversized_fields_are_stored_as_the_truncation_marker(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    step = new_step_id()
    big_output = {"rows": ["x" * 100] * 1000}
    small_input = {"query": "weather"}
    long_trace = "frame\n" * 20000  # 120 KB
    response = post_events(
        db_client,
        auth,
        execution.id,
        [
            ev.step_started(1, step, input=small_input),
            ev.step_failed(
                2,
                step,
                10,
                output=big_output,
                error={"type": "ValueError", "message": "bad", "stacktrace": long_trace},
            ),
        ],
    )
    assert response.status_code == 202
    stored = steps_of(db_session, execution)[0]
    assert stored.input == small_input
    assert set(stored.output) == {"_truncated", "original_bytes", "preview"}
    assert stored.output["_truncated"] is True
    assert stored.output["original_bytes"] == 103010
    assert stored.output["preview"] == json.dumps(big_output, separators=(",", ":"))[:2000]
    assert len(stored.output["preview"]) == 2000
    # The error keeps its ErrorInfo shape; only the stack trace text is cut, keeping its tail.
    assert set(stored.error) == {"type", "message", "stacktrace"}
    assert stored.error["stacktrace"].startswith("[truncated: 120000 bytes in total]\n")
    assert stored.error["stacktrace"].endswith("frame\n")
    assert len(stored.error["stacktrace"]) < 66000

    payload = db_session.scalar(
        select(Event.payload).where(Event.execution_id == execution.id, Event.seq == 2)
    )
    assert payload["output"] == stored.output  # the evidence log holds the same marker


def test_step_metadata_from_completion_is_laid_over_the_start(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    step = new_step_id()
    post_events(
        db_client,
        auth,
        execution.id,
        [
            ev.step_started(1, step, metadata={"provider": "fake", "cached": False}),
            ev.step_completed(2, step, 10, metadata={"cached": True, "http_status": 200}),
        ],
    )
    assert steps_of(db_session, execution)[0].metadata_ == {
        "provider": "fake",
        "cached": True,
        "http_status": 200,
    }


def test_durations_come_from_client_timestamps_and_never_go_negative(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    step = new_step_id()
    post_events(
        db_client,
        auth,
        execution.id,
        [ev.step_started(1, step, 500), ev.step_completed(2, step, 400), ev.execution_completed(3, -50)],
    )
    assert steps_of(db_session, execution)[0].duration_ms == 0
    assert execution.duration_ms == 0


def test_ingest_requires_the_api_key_and_a_known_execution(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    body = {"events": [ev.log(1)]}
    assert db_client.post(f"/api/v1/executions/{execution.id}/events", json=body).status_code == 401
    unknown = db_client.post(f"/api/v1/executions/exe_{'0' * 32}/events", json=body, headers=auth)
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "not_found"
    assert_nothing_stored(db_session, execution)


def bad(event: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {**event, **changes}


@pytest.mark.parametrize(
    "events",
    [
        [],
        [ev.log(seq) for seq in range(1, 502)],
        [bad(ev.log(1), seq=0)],
        [bad(ev.log(1), type="step.paused")],
        [bad(ev.log(1), timestamp="2026-11-14T10:00:00")],
        [bad(ev.log(1), timestamp=1731580325)],
        [bad(ev.log(1), payload={"level": "loud", "message": "x"})],
        [bad(ev.execution_timed_out(1), payload={"reason": "slow"})],
        [ev.step_started(1, "step-1")],
        [ev.step_started(1, "stp_" + "a" * 32, step_type="thinking")],
        [ev.step_started(1, "stp_" + "a" * 32, attempt=0)],
        [ev.step_completed(1, "stp_" + "a" * 32, tokens_input=-5)],
        [bad(ev.execution_failed(1), payload={})],
    ],
    ids=[
        "empty",
        "501-events",
        "seq-0",
        "unknown-type",
        "naive-timestamp",
        "epoch-timestamp",
        "bad-log-level",
        "extra-payload-key",
        "bad-step-id",
        "bad-step-type",
        "attempt-0",
        "negative-tokens",
        "failed-without-error",
    ],
)
def test_malformed_batches_are_rejected(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution, events: list
) -> None:
    response = post_events(db_client, auth, execution.id, events)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"
    assert_nothing_stored(db_session, execution)


def test_a_500_event_batch_is_accepted(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    response = post_events(db_client, auth, execution.id, [ev.log(seq) for seq in range(1, 501)])
    assert response.json() == {"accepted": 500, "duplicates": 0, "execution_status": "running"}


def test_concurrent_identical_batches_are_stored_once(migrated_database: None) -> None:
    """Two retries of one batch racing on separate connections: one stores it, the other sees duplicates."""
    engine = get_engine()
    with Session(engine, expire_on_commit=False) as setup:
        execution = make_execution(setup, make_agent(setup))
        setup.commit()
    steps = [new_step_id() for _ in range(20)]
    events: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        events += [ev.step_started(2 * index + 1, step), ev.step_completed(2 * index + 2, step, 5)]
    batch = IngestRequest.model_validate({"events": events}).events

    results: list[Any] = []
    barrier = threading.Barrier(4)

    def worker() -> None:
        with Session(engine, expire_on_commit=False) as session:
            barrier.wait()
            try:
                results.append(ingest_events(session, execution.id, batch))
            except Exception as exc:  # reported by the assertion below
                results.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert sorted((result.response.accepted, result.response.duplicates) for result in results) == [
            (0, 40),
            (0, 40),
            (0, 40),
            (40, 0),
        ], results
        with Session(engine) as check:
            assert (
                check.scalar(
                    select(func.count()).select_from(Event).where(Event.execution_id == execution.id)
                )
                == 40
            )
            ordinals = check.scalars(
                select(Step.ordinal).where(Step.execution_id == execution.id).order_by(Step.ordinal)
            ).all()
            assert ordinals == list(range(1, 21))
            assert check.get(Execution, execution.id).step_count == 20
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(Event).where(Event.execution_id == execution.id))
            cleanup.execute(delete(Step).where(Step.execution_id == execution.id))
            cleanup.execute(delete(Execution).where(Execution.id == execution.id))
            cleanup.execute(delete(Agent).where(Agent.id == execution.agent_id))
            cleanup.commit()
