"""Contract §6: traces and the raw event log."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import ids
from app.models import Execution, Step
from app.services.traces import step_depths
from tests import events as ev
from tests.events import new_step_id, post_events
from tests.factories import T0, make_agent, make_anomaly, make_execution
from tests.test_executions import DETAIL_KEYS

TRACE_KEYS = {"execution", "steps", "anomalies", "event_count"}
STEP_KEYS = {
    "id", "execution_id", "parent_step_id", "ordinal", "depth", "name", "type", "status", "started_at",
    "ended_at", "duration_ms", "offset_ms", "input", "output", "error", "tool_name", "model", "tokens_input",
    "tokens_output", "attempt", "metadata",
}  # fmt: skip
ANOMALY_KEYS = {
    "id", "type", "severity", "status", "agent_id", "agent_name", "execution_id", "detected_at", "rule_id",
    "title", "explanation", "evidence",
}  # fmt: skip
EVIDENCE_KEYS = {"kind", "label", "ref_id", "field", "observed", "expected", "excerpt"}
EVENT_KEYS = {"id", "seq", "type", "timestamp", "received_at", "payload"}


@pytest.fixture
def execution(db_session: Session) -> Execution:
    return make_execution(db_session, make_agent(db_session, name="Research Assistant"))


def fake_step(step_id: str, parent: str | None) -> Step:
    return Step(id=step_id, parent_step_id=parent)


@pytest.mark.parametrize(
    ("parents", "expected"),
    [
        ({"a": None, "b": None}, {"a": 0, "b": 0}),
        ({"a": None, "b": "a", "c": "b", "d": "c", "e": "a"}, {"a": 0, "b": 1, "c": 2, "d": 3, "e": 1}),
        ({"c": "b", "b": "a", "a": None}, {"a": 0, "b": 1, "c": 2}),  # children listed before parents
        ({"a": "missing", "b": "a"}, {"a": 0, "b": 1}),  # unknown parent: treated as a root
        ({"a": "a"}, {"a": 0}),  # self-parent
        ({"a": "b", "b": "a", "c": "a"}, {"a": 1, "b": 0, "c": 2}),  # loop: broken, never infinite
    ],
)
def test_step_depths(parents: dict[str, str | None], expected: dict[str, int]) -> None:
    assert step_depths([fake_step(step_id, parent) for step_id, parent in parents.items()]) == expected


def test_trace_of_a_nested_run(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    root, child, grandchild, sibling, retry = (new_step_id() for _ in range(5))
    post_events(
        db_client,
        auth,
        execution.id,
        [
            ev.step_started(1, root, 10, name="research", input={"q": "x"}),
            ev.step_started(
                2,
                child,
                20,
                name="web_search",
                step_type="tool_call",
                tool_name="web_search",
                parent_step_id=root,
            ),
            ev.step_started(3, grandchild, 25, name="http_get", step_type="custom", parent_step_id=child),
            ev.step_completed(4, grandchild, 125, output={"status": 500}),
            ev.step_failed(5, child, 130, error={"type": "HTTPError", "message": "500"}),
            ev.step_started(
                6,
                retry,
                200,
                name="web_search",
                step_type="tool_call",
                tool_name="web_search",
                parent_step_id=root,
                attempt=2,
                metadata={"retry_reason": "HTTPError"},
            ),
            ev.step_completed(7, retry, 450, output={"results": []}, tokens_input=5, tokens_output=7),
            ev.step_completed(8, root, 460),
            ev.step_started(
                9, sibling, 470, name="summarize", step_type="llm_call", model="claude-fable-5-2"
            ),
        ],
    )
    anomaly = make_anomaly(db_session, execution, type="excessive_retries")
    make_anomaly(
        db_session, make_execution(db_session, make_agent(db_session))
    )  # another execution's anomaly

    response = db_client.get(f"/api/v1/executions/{execution.id}/trace")
    assert response.status_code == 200, response.text
    trace = response.json()
    assert set(trace) == TRACE_KEYS
    assert set(trace["execution"]) == DETAIL_KEYS
    assert (trace["execution"]["id"], trace["execution"]["status"], trace["execution"]["step_count"]) == (
        execution.id,
        "running",
        5,
    )
    assert trace["event_count"] == 9

    steps = trace["steps"]
    assert all(set(step) == STEP_KEYS for step in steps)
    assert [step["id"] for step in steps] == [root, child, grandchild, retry, sibling]
    assert [step["ordinal"] for step in steps] == [1, 2, 3, 4, 5]
    assert [step["depth"] for step in steps] == [0, 1, 2, 1, 0]
    assert [step["parent_step_id"] for step in steps] == [None, root, child, root, None]
    assert [step["offset_ms"] for step in steps] == [10, 20, 25, 200, 470]
    assert [step["duration_ms"] for step in steps] == [450, 110, 100, 250, None]
    assert [step["status"] for step in steps] == ["completed", "failed", "completed", "completed", "running"]
    assert [step["attempt"] for step in steps] == [1, 1, 1, 2, 1]
    assert all(step["execution_id"] == execution.id for step in steps)

    failed, retried, running = steps[1], steps[3], steps[4]
    assert failed["error"] == {"type": "HTTPError", "message": "500", "stacktrace": None}
    assert (failed["type"], failed["tool_name"], failed["model"]) == ("tool_call", "web_search", None)
    assert (retried["tokens_input"], retried["tokens_output"]) == (5, 7)
    assert retried["metadata"] == {"retry_reason": "HTTPError"}
    assert retried["started_at"] == ev.at(200) and retried["ended_at"] == ev.at(450)
    assert (running["ended_at"], running["duration_ms"], running["output"], running["error"]) == (
        None,
        None,
        None,
        None,
    )
    assert (running["model"], running["tool_name"]) == ("claude-fable-5-2", None)
    assert steps[0]["input"] == {"q": "x"} and steps[0]["metadata"] == {}

    assert [item["id"] for item in trace["anomalies"]] == [anomaly.id]
    listed = trace["anomalies"][0]
    assert set(listed) == ANOMALY_KEYS
    assert (listed["agent_name"], listed["execution_id"], listed["type"]) == (
        "Research Assistant",
        execution.id,
        "excessive_retries",
    )
    assert set(listed["evidence"][0]) == EVIDENCE_KEYS
    assert trace["execution"]["anomaly_count"] == 1


def test_trace_of_a_completed_run_with_no_steps(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    """A ghost completion has an empty trace; that emptiness is the evidence and must be served."""
    post_events(db_client, auth, execution.id, [ev.execution_completed(1, 40, output={"status": "ok"})])
    trace = db_client.get(f"/api/v1/executions/{execution.id}/trace").json()
    assert (trace["steps"], trace["event_count"]) == ([], 1)
    assert (trace["execution"]["status"], trace["execution"]["step_count"]) == ("completed", 0)
    # ...and the anomaly engine flags it on the spot.
    assert [(item["type"], item["severity"]) for item in trace["anomalies"]] == [
        ("ghost_completion", "critical")
    ]
    assert trace["execution"]["anomaly_count"] == 1


def test_trace_with_no_events_yet(db_client: TestClient, db_session: Session, execution: Execution) -> None:
    trace = db_client.get(f"/api/v1/executions/{execution.id}/trace").json()
    assert (trace["steps"], trace["anomalies"], trace["event_count"]) == ([], [], 0)


def test_orphan_parents_and_early_timestamps_do_not_break_the_trace(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    orphan, child, early = new_step_id(), new_step_id(), new_step_id()
    post_events(
        db_client,
        auth,
        execution.id,
        [
            ev.step_started(1, orphan, 5, parent_step_id=ids.new_id(ids.STEP)),
            ev.step_started(2, child, 6, parent_step_id=orphan),
            ev.step_started(3, early, -500),  # client clock behind the execution start
        ],
    )
    steps = db_client.get(f"/api/v1/executions/{execution.id}/trace").json()["steps"]
    assert [step["depth"] for step in steps] == [0, 1, 0]
    assert [step["offset_ms"] for step in steps] == [5, 6, 0]
    assert steps[0]["parent_step_id"] is not None  # stored as sent; only the layout treats it as a root


def test_offsets_are_relative_to_the_execution_start(
    db_client: TestClient, db_session: Session, auth: dict
) -> None:
    later = make_execution(db_session, make_agent(db_session), started_at=T0 + timedelta(seconds=30))
    post_events(db_client, auth, later.id, [ev.step_started(1, new_step_id(), 31250)])
    assert db_client.get(f"/api/v1/executions/{later.id}/trace").json()["steps"][0]["offset_ms"] == 1250


def test_raw_events_are_served_in_seq_order_exactly_as_stored(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    step = new_step_id()
    post_events(
        db_client,
        auth,
        execution.id,
        [
            ev.execution_failed(4, 300),
            ev.log(3, 250, message="about to fail", level="warning"),
            ev.step_failed(2, step, 200, output={"rows": ["x" * 100] * 1000}),
            ev.step_started(1, step, 100, name="parse_results"),
        ],
    )
    response = db_client.get(f"/api/v1/executions/{execution.id}/events")
    assert response.status_code == 200, response.text
    page = response.json()
    assert set(page) == {"items", "total", "limit", "offset"}
    assert (page["total"], page["limit"], page["offset"]) == (4, 50, 0)
    items = page["items"]
    assert all(set(item) == EVENT_KEYS for item in items)
    assert [item["seq"] for item in items] == [1, 2, 3, 4]
    assert [item["type"] for item in items] == ["step.started", "step.failed", "log", "execution.failed"]
    assert [item["timestamp"] for item in items] == [ev.at(100), ev.at(200), ev.at(250), ev.at(300)]
    assert all(item["id"].startswith("evt_") and item["received_at"].endswith("Z") for item in items)
    assert items[0]["payload"] == {
        "step_id": step,
        "parent_step_id": None,
        "name": "parse_results",
        "step_type": "reasoning",
        "input": None,
        "tool_name": None,
        "model": None,
        "attempt": 1,
        "metadata": {},
    }
    assert items[1]["payload"]["output"]["_truncated"] is True
    assert items[1]["payload"]["error"] == ev.KEY_ERROR
    assert items[2]["payload"] == {"level": "warning", "message": "about to fail", "step_id": None}
    assert items[3]["payload"] == {"error": ev.KEY_ERROR}

    second = db_client.get(f"/api/v1/executions/{execution.id}/events?limit=2&offset=2").json()
    assert [item["seq"] for item in second["items"]] == [3, 4]
    assert (second["total"], second["limit"], second["offset"]) == (4, 2, 2)


def test_raw_events_of_an_execution_without_events(
    db_client: TestClient, db_session: Session, execution: Execution
) -> None:
    assert db_client.get(f"/api/v1/executions/{execution.id}/events").json() == {
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


@pytest.mark.parametrize("path", ["trace", "events"])
@pytest.mark.parametrize("execution_id", ["exe_" + "0" * 32, "nope"])
def test_unknown_execution_is_not_found(
    db_client: TestClient, db_session: Session, path: str, execution_id: str
) -> None:
    response = db_client.get(f"/api/v1/executions/{execution_id}/{path}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
