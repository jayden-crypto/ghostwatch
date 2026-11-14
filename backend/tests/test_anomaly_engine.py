"""The anomaly engine against stored data: baselines, the terminal hook in ingestion, idempotency, the API."""

import logging
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Agent, Anomaly, Execution
from app.services.anomaly.baseline import load_baseline, load_recent_runs
from app.services.anomaly.engine import evaluate
from tests import events as ev
from tests.events import new_step_id, post_events
from tests.factories import T0, make_agent, make_anomaly, make_execution, make_step
from tests.test_traces import ANOMALY_KEYS, EVIDENCE_KEYS

HOUR = timedelta(hours=1)


@pytest.fixture
def agent(db_session: Session) -> Agent:
    return make_agent(db_session, slug="research-assistant", name="Research Assistant")


def seed_baseline(session: Session, agent: Agent, runs: int = 20, **values: object) -> list[Execution]:
    """Completed runs before T0, newest first: 1,000 ms, 1,000 tokens, 3 steps, one web_search call each."""
    history = []
    for index in range(1, runs + 1):
        defaults = {
            "status": "completed",
            "started_at": T0 - index * HOUR,
            "duration_ms": 1000,
            "tokens_input": 800,
            "tokens_output": 200,
            "step_count": 3,
        }
        run = make_execution(session, agent, **{**defaults, **values})
        make_step(session, run, 1, name="web_search", type="tool_call", tool_name="web_search")
        history.append(run)
    return history


def anomalies_of(session: Session, execution_id: str) -> dict[str, Anomaly]:
    rows = session.scalars(select(Anomaly).where(Anomaly.execution_id == execution_id)).all()
    return {row.type: row for row in rows}


def finish_run(client: TestClient, auth: dict, execution: Execution, events: list[dict]) -> None:
    response = post_events(client, auth, execution.id, events)
    assert response.status_code == 202, response.text


def healthy_steps(end_ms: int) -> list[dict]:
    step = new_step_id()
    return [
        ev.step_started(1, step, 10, name="web_search", step_type="tool_call", tool_name="web_search"),
        ev.step_completed(2, step, end_ms - 10, tokens_input=800, tokens_output=200),
        ev.execution_completed(3, end_ms),
    ]


def test_baseline_is_the_last_20_completed_non_replay_runs_before_this_one(
    db_session: Session, agent: Agent
) -> None:
    current = make_execution(db_session, agent, started_at=T0)
    newest_first = []
    for index in range(1, 26):  # 25 completed runs; only the newest 20 count
        run = make_execution(
            db_session, agent, status="completed", started_at=T0 - index * HOUR, duration_ms=100 * index,
            tokens_input=index if index % 2 else None, step_count=index,
        )  # fmt: skip
        make_step(db_session, run, 1, tool_name="web_search" if index <= 20 else "legacy_tool")
        newest_first.append(run)
    # None of these may enter the baseline:
    make_execution(db_session, agent, status="failed", started_at=T0 - HOUR / 2, duration_ms=1)
    make_execution(db_session, agent, status="timed_out", started_at=T0 - HOUR / 3, duration_ms=2)
    make_execution(db_session, agent, status="running", started_at=T0 - HOUR / 4)
    replay = make_execution(
        db_session,
        agent,
        status="completed",
        started_at=T0 - HOUR / 5,
        duration_ms=3,
        replay_of=newest_first[0].id,
    )
    make_step(db_session, replay, 1, tool_name="replay_only_tool")
    make_execution(
        db_session, agent, status="completed", started_at=T0 + HOUR, duration_ms=4
    )  # started later
    other_agent = make_agent(db_session)
    make_execution(db_session, other_agent, status="completed", started_at=T0 - HOUR, duration_ms=5)

    baseline = load_baseline(db_session, current)
    assert baseline.durations_ms == [100 * index for index in range(1, 21)]
    assert baseline.token_totals == [index for index in range(1, 21) if index % 2]
    assert baseline.step_counts == list(range(1, 21))
    assert baseline.tool_names == {"web_search"}
    assert (baseline.runs, baseline.is_sufficient, baseline.max_step_count) == (20, True, 20)


def test_recent_runs_are_terminal_non_replay_runs_newest_first_starting_with_this_one(
    db_session: Session, agent: Agent
) -> None:
    current = make_execution(db_session, agent, status="failed", started_at=T0)
    make_step(db_session, current, 1, status="failed", tool_name="retrieve_kb")
    make_step(db_session, current, 2, status="completed", tool_name="web_search")
    older = make_execution(db_session, agent, status="timed_out", started_at=T0 - HOUR)
    make_step(db_session, older, 1, status="failed", tool_name="retrieve_kb")
    make_step(db_session, older, 2, status="failed")  # a failed step without a tool
    make_execution(db_session, agent, status="running", started_at=T0 - HOUR / 2)
    make_execution(db_session, agent, status="failed", started_at=T0 - HOUR / 3, replay_of=older.id)
    for index in range(2, 14):
        make_execution(db_session, agent, status="completed", started_at=T0 - index * HOUR)

    recent = load_recent_runs(db_session, current)
    assert len(recent) == 10
    assert (recent[0].execution_id, recent[0].status, recent[0].failed_tools) == (
        current.id,
        "failed",
        {"retrieve_kb"},
    )
    assert (recent[1].execution_id, recent[1].status, recent[1].failed_tools) == (
        older.id,
        "timed_out",
        {"retrieve_kb"},
    )
    assert [run.status for run in recent[2:]] == ["completed"] * 8


def test_a_slow_run_is_flagged_when_it_finishes(
    db_client: TestClient, db_session: Session, auth: dict, agent: Agent
) -> None:
    seed_baseline(db_session, agent)
    slow = make_execution(db_session, agent, started_at=T0)
    finish_run(db_client, auth, slow, healthy_steps(end_ms=4000))

    trace = db_client.get(f"/api/v1/executions/{slow.id}/trace").json()
    (anomaly,) = trace["anomalies"]
    assert set(anomaly) == ANOMALY_KEYS and all(set(item) == EVIDENCE_KEYS for item in anomaly["evidence"])
    assert (anomaly["type"], anomaly["severity"], anomaly["status"], anomaly["rule_id"]) == (
        "duration_spike", "medium", "open", "duration_spike.v1",
    )  # fmt: skip
    assert (anomaly["agent_id"], anomaly["agent_name"], anomaly["execution_id"]) == (
        agent.id,
        "Research Assistant",
        slow.id,
    )
    assert anomaly["title"] == "Duration 4.0× above baseline"
    assert anomaly["explanation"].startswith(
        "Execution took 4,000 ms. Baseline median for research-assistant is 1,000 ms over 20 runs "
        "(p95 1,000 ms)."
    )
    assert anomaly["evidence"][0]["ref_id"] == slow.id and anomaly["evidence"][0]["observed"] == 4000
    assert trace["execution"]["anomaly_count"] == 1

    stats = db_client.get(f"/api/v1/agents/{agent.id}").json()["stats"]
    assert (stats["open_anomalies"], stats["health"]) == (
        1,
        "healthy",
    )  # a medium anomaly does not degrade health


def test_a_normal_run_raises_nothing(
    db_client: TestClient, db_session: Session, auth: dict, agent: Agent
) -> None:
    seed_baseline(db_session, agent)
    normal = make_execution(db_session, agent, started_at=T0)
    finish_run(db_client, auth, normal, healthy_steps(end_ms=1100))
    assert anomalies_of(db_session, normal.id) == {}


def test_baseline_rules_wait_for_five_runs(
    db_client: TestClient, db_session: Session, auth: dict, agent: Agent, caplog: pytest.LogCaptureFixture
) -> None:
    seed_baseline(db_session, agent, runs=4)
    slow = make_execution(db_session, agent, started_at=T0)
    with caplog.at_level(logging.INFO, logger="ghostwatch"):
        finish_run(db_client, auth, slow, [ev.execution_failed(1, 900000)])
    assert anomalies_of(db_session, slow.id) == {}
    assert any(
        "skipped" in record.message and "4 baseline run(s), 5 needed" in record.message
        for record in caplog.records
    )

    seed_baseline(db_session, agent, runs=1, started_at=T0 - 30 * HOUR)  # a fifth completed run
    slow_again = make_execution(db_session, agent, started_at=T0)
    finish_run(db_client, auth, slow_again, healthy_steps(end_ms=900000))
    assert set(anomalies_of(db_session, slow_again.id)) == {"duration_spike"}
    assert anomalies_of(db_session, slow_again.id)["duration_spike"].severity == "high"


def test_token_spike_and_unexpected_pattern_from_ingested_events(
    db_client: TestClient, db_session: Session, auth: dict, agent: Agent
) -> None:
    seed_baseline(db_session, agent)
    run = make_execution(db_session, agent, started_at=T0)
    search, email = new_step_id(), new_step_id()
    finish_run(
        db_client,
        auth,
        run,
        [
            ev.step_started(1, search, 10, name="web_search", step_type="tool_call", tool_name="web_search"),
            ev.step_completed(2, search, 400, tokens_input=4000, tokens_output=500),
            ev.step_started(3, email, 410, name="send_email", step_type="tool_call", tool_name="send_email"),
            ev.step_completed(4, email, 500),
            ev.execution_completed(5, 900),
        ],
    )
    raised = anomalies_of(db_session, run.id)
    assert {name: anomaly.severity for name, anomaly in raised.items()} == {
        "token_spike": "high",
        "unexpected_pattern": "low",
    }
    assert raised["token_spike"].title == "Token usage 4.5× above baseline"
    assert raised["unexpected_pattern"].evidence[0]["ref_id"] == email


def test_ghost_completion_is_flagged_when_the_agent_reports_success(
    db_client: TestClient, db_session: Session, auth: dict
) -> None:
    agent = make_agent(db_session, slug="invoice-processor", name="Invoice Processor")
    run = make_execution(
        db_session, agent, config={"expected_steps": ["extract_fields", "validate", "submit_invoice"]}
    )
    extract, validate = new_step_id(), new_step_id()
    finish_run(
        db_client,
        auth,
        run,
        [
            ev.step_started(1, extract, 10, name="extract_fields"),
            ev.step_completed(2, extract, 100),
            ev.step_started(3, validate, 110, name="validate"),
            ev.step_completed(4, validate, 200, output={"valid": False}),
            ev.execution_completed(5, 250, output={"status": "submitted"}),
        ],
    )
    detail = db_client.get(f"/api/v1/executions/{run.id}").json()
    assert (detail["status"], detail["anomaly_count"]) == ("completed", 1)
    (ghost,) = db_client.get(f"/api/v1/anomalies?execution_id={run.id}").json()["items"]
    assert (ghost["type"], ghost["severity"]) == ("ghost_completion", "critical")
    assert ghost["title"] == "Reported completed, but submit_invoice never completed"
    assert ghost["evidence"][0]["expected"] == ["extract_fields", "validate", "submit_invoice"]
    assert ghost["evidence"][0]["observed"] == ["extract_fields", "validate"]
    assert (
        db_client.get(f"/api/v1/agents/{agent.id}").json()["stats"]["health"] == "failing"
    )  # open critical anomaly


def test_retries_and_repeated_tool_failure_in_one_execution(
    db_client: TestClient, db_session: Session, auth: dict, agent: Agent
) -> None:
    run = make_execution(db_session, agent)
    events, seq = [], 0
    step_ids = []
    for attempt in (1, 2, 3):
        step = new_step_id()
        step_ids.append(step)
        events.append(
            ev.step_started(
                seq + 1,
                step,
                attempt * 100,
                name="retrieve_kb",
                step_type="tool_call",
                tool_name="retrieve_kb",
                attempt=attempt,
            )
        )
        events.append(
            ev.step_failed(
                seq + 2,
                step,
                attempt * 100 + 50,
                error={"type": "HTTPError", "message": "429 Too Many Requests"},
            )
        )
        seq += 2
    events.append(
        ev.execution_failed(seq + 1, 500, error={"type": "HTTPError", "message": "429 Too Many Requests"})
    )
    finish_run(db_client, auth, run, events)

    raised = anomalies_of(db_session, run.id)
    assert {name: anomaly.severity for name, anomaly in raised.items()} == {
        "repeated_tool_failure": "high",
        "excessive_retries": "medium",
    }
    assert [item["ref_id"] for item in raised["repeated_tool_failure"].evidence] == step_ids
    assert raised["repeated_tool_failure"].evidence[0]["excerpt"] == "429 Too Many Requests"


def test_evaluating_twice_creates_nothing_new(
    db_client: TestClient, db_session: Session, auth: dict, agent: Agent
) -> None:
    seed_baseline(db_session, agent)
    run = make_execution(db_session, agent, started_at=T0, config={"expected_steps": ["submit"]})
    finish_run(db_client, auth, run, healthy_steps(end_ms=9000))
    first = anomalies_of(db_session, run.id)
    assert set(first) == {"duration_spike", "ghost_completion"}

    assert evaluate(db_session, run) == []
    assert evaluate(db_session, run) == []
    again = anomalies_of(db_session, run.id)
    assert {name: anomaly.id for name, anomaly in again.items()} == {
        name: anomaly.id for name, anomaly in first.items()
    }
    assert db_session.scalar(select(func.count()).select_from(Anomaly)) == 2


def test_repeated_timeouts_is_raised_on_the_third_timeout_only(
    db_client: TestClient, db_session: Session, auth: dict, agent: Agent
) -> None:
    earlier = [
        make_execution(db_session, agent, status="timed_out", started_at=T0 - index * HOUR)
        for index in (1, 2)
    ]
    make_execution(db_session, agent, status="completed", started_at=T0 - 3 * HOUR)
    third = make_execution(db_session, agent, started_at=T0)
    finish_run(db_client, auth, third, [ev.execution_timed_out(1, 300000)])
    raised = anomalies_of(db_session, third.id)
    assert set(raised) == {"repeated_timeouts"}
    assert raised["repeated_timeouts"].severity == "high"
    assert [item["ref_id"] for item in raised["repeated_timeouts"].evidence] == [
        third.id,
        earlier[0].id,
        earlier[1].id,
    ]

    healthy = make_execution(db_session, agent, started_at=T0 + HOUR)
    finish_run(db_client, auth, healthy, healthy_steps(end_ms=500))
    assert anomalies_of(db_session, healthy.id) == {}


def test_repeated_tool_failure_across_three_executions(
    db_client: TestClient, db_session: Session, auth: dict, agent: Agent
) -> None:
    earlier = []
    for index in (1, 2):
        run = make_execution(db_session, agent, status="failed", started_at=T0 - index * HOUR)
        make_step(db_session, run, 1, name="web_search", status="failed", tool_name="web_search")
        earlier.append(run)
    current = make_execution(db_session, agent, started_at=T0)
    step = new_step_id()
    finish_run(
        db_client,
        auth,
        current,
        [
            ev.step_started(1, step, 10, name="web_search", step_type="tool_call", tool_name="web_search"),
            ev.step_failed(2, step, 20, error={"type": "HTTPError", "message": "503"}),
            ev.execution_failed(3, 30),
        ],
    )
    (anomaly,) = anomalies_of(db_session, current.id).values()
    assert (anomaly.type, anomaly.title) == (
        "repeated_tool_failure",
        "Tool web_search failed in 3 executions in a row",
    )
    assert [item["ref_id"] for item in anomaly.evidence] == [step, earlier[0].id, earlier[1].id]


def test_replays_are_evaluated_but_never_become_history(
    db_client: TestClient, db_session: Session, auth: dict, agent: Agent
) -> None:
    seed_baseline(db_session, agent, runs=5)
    original = make_execution(db_session, agent, status="failed", started_at=T0 - HOUR / 2)
    replay = make_execution(
        db_session, agent, started_at=T0, replay_of=original.id, config={"expected_steps": ["never"]}
    )
    finish_run(db_client, auth, replay, healthy_steps(end_ms=50000))
    assert set(anomalies_of(db_session, replay.id)) == {"duration_spike", "ghost_completion"}

    after = make_execution(db_session, agent, started_at=T0 + HOUR)
    assert 50000 not in load_baseline(db_session, after).durations_ms
    assert replay.id not in [run.execution_id for run in load_recent_runs(db_session, after)]


def test_list_anomalies_filters_sorts_and_paginates(
    db_client: TestClient, db_session: Session, agent: Agent
) -> None:
    other = make_agent(db_session, name="Invoice Processor")
    first, second = make_execution(db_session, agent), make_execution(db_session, other)
    minute = timedelta(minutes=1)
    a = make_anomaly(db_session, first, type="duration_spike", severity="medium", detected_at=T0)
    b = make_anomaly(db_session, first, type="ghost_completion", severity="critical", detected_at=T0 + minute)
    c = make_anomaly(
        db_session,
        second,
        type="excessive_retries",
        severity="medium",
        status="resolved",
        detected_at=T0 + 2 * minute,
    )
    d = make_anomaly(
        db_session,
        second,
        type="stale_execution",
        severity="high",
        status="acknowledged",
        detected_at=T0 + 3 * minute,
    )
    names = {a.id: "a", b.id: "b", c.id: "c", d.id: "d"}

    def listed(query: str = "") -> str:
        response = db_client.get(f"/api/v1/anomalies{query}")
        assert response.status_code == 200, response.text
        page = response.json()
        assert all(set(item) == ANOMALY_KEYS for item in page["items"])
        return "".join(names[item["id"]] for item in page["items"])

    page = db_client.get("/api/v1/anomalies").json()
    assert set(page) == {"items", "total", "limit", "offset"} and (
        page["total"],
        page["limit"],
        page["offset"],
    ) == (4, 50, 0)
    assert listed() == "dcba"  # newest first
    assert listed("?sort=detected_at") == "abcd"
    assert listed(f"?agent_id={agent.id}") == "ba"
    assert listed(f"?execution_id={second.id}") == "dc"
    assert listed("?type=ghost_completion") == "b"
    assert listed("?type=ghost_completion,stale_execution") == "db"
    assert listed("?severity=medium") == "ca"
    assert listed("?severity=high,critical") == "db"
    assert listed("?status=open") == "ba"
    assert listed("?status=acknowledged,resolved") == "dc"
    assert listed(f"?agent_id={agent.id}&severity=critical&status=open") == "b"
    assert listed("?severity=low") == ""
    assert listed("?limit=2&offset=1") == "cb"
    assert db_client.get("/api/v1/anomalies?limit=1").json()["total"] == 4
    assert (
        db_client.get("/api/v1/anomalies?status=open").json()["items"][0]["agent_name"]
        == "Research Assistant"
    )

    one = db_client.get(f"/api/v1/anomalies/{d.id}")
    assert one.status_code == 200 and one.json()["id"] == d.id and set(one.json()) == ANOMALY_KEYS


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/anomalies?type=weird", 422, "validation_error"),
        ("/anomalies?severity=urgent", 422, "validation_error"),
        ("/anomalies?status=closed", 422, "validation_error"),
        ("/anomalies?sort=severity", 400, "bad_request"),
        ("/anomalies/anm_" + "0" * 32, 404, "not_found"),
        ("/anomalies/nope", 404, "not_found"),
    ],
)
def test_anomalies_api_rejects_bad_requests(
    db_client: TestClient, db_session: Session, path: str, status: int, code: str
) -> None:
    response = db_client.get(f"/api/v1{path}")
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
