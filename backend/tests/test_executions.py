"""Contract §4: Executions."""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Execution
from tests.factories import T0, make_agent, make_anomaly, make_execution, make_investigation, make_replay

SUMMARY_KEYS = {
    "id",
    "agent_id",
    "agent_name",
    "status",
    "started_at",
    "ended_at",
    "duration_ms",
    "step_count",
    "tokens_total",
    "cost_usd",
    "anomaly_count",
    "has_investigation",
    "replay_of",
    "error",
}
DETAIL_KEYS = SUMMARY_KEYS | {
    "input",
    "output",
    "config",
    "tokens_input",
    "tokens_output",
    "tags",
    "replay_ids",
}
MINUTE = timedelta(minutes=1)


def test_create_execution(db_client: TestClient, db_session: Session, auth: dict) -> None:
    agent = make_agent(db_session, name="Research Assistant")
    before = datetime.now(UTC)
    response = db_client.post(
        "/api/v1/executions",
        json={
            "agent_id": agent.id,
            "input": {"question": "What changed?"},
            "config": {"model": "claude-fable-5-2", "expected_steps": ["web_search"], "seed": 7},
            "tags": ["demo"],
        },
        headers=auth,
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == DETAIL_KEYS
    assert re.fullmatch(r"exe_[0-9a-f]{32}", body["id"])
    assert (body["status"], body["agent_id"], body["agent_name"]) == (
        "running",
        agent.id,
        "Research Assistant",
    )
    assert body["input"] == {"question": "What changed?"}
    assert body["config"] == {
        "model": "claude-fable-5-2",
        "params": {},
        "expected_steps": ["web_search"],
        "timeout_ms": None,
        "seed": 7,
    }
    assert body["tags"] == ["demo"]
    for key in (
        "ended_at",
        "duration_ms",
        "output",
        "tokens_total",
        "tokens_input",
        "tokens_output",
        "cost_usd",
    ):
        assert body[key] is None, key
    assert (body["step_count"], body["anomaly_count"], body["has_investigation"]) == (0, 0, False)
    assert (body["replay_of"], body["replay_ids"], body["error"]) == (None, [], None)

    stored = db_session.get(Execution, body["id"])
    assert before <= stored.started_at <= datetime.now(UTC)
    assert stored.last_event_at >= before  # the stale sweeper measures from here


def test_create_execution_with_defaults_and_explicit_start(
    db_client: TestClient, db_session: Session, auth: dict
) -> None:
    agent = make_agent(db_session)
    response = db_client.post(
        "/api/v1/executions",
        json={"agent_id": agent.id, "input": None, "config": {}, "started_at": "2026-11-10T15:30:00+05:30"},
        headers=auth,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["started_at"] == "2026-11-10T10:00:00.000Z"
    assert body["config"] == {"model": None, "params": {}, "expected_steps": None, "timeout_ms": None}
    assert (body["input"], body["tags"]) == (None, [])


def test_create_replay_execution(db_client: TestClient, db_session: Session, auth: dict) -> None:
    agent = make_agent(db_session)
    original = make_execution(db_session, agent, status="failed")
    replay = make_replay(db_session, original, status="claimed")
    response = db_client.post(
        "/api/v1/executions",
        json={
            "agent_id": agent.id,
            "input": {},
            "config": {},
            "replay_of": original.id,
            "replay_id": replay.id,
        },
        headers=auth,
    )
    assert response.status_code == 201
    assert response.json()["replay_of"] == original.id
    detail = db_client.get(f"/api/v1/executions/{original.id}").json()
    assert detail["replay_ids"] == [replay.id]


@pytest.mark.parametrize(
    ("patch", "status", "code"),
    [
        ({"agent_id": "agt_" + "0" * 32}, 404, "not_found"),
        ({"replay_of": "exe_" + "0" * 32}, 404, "not_found"),
        ({"agent_id": "research-assistant"}, 422, "validation_error"),
        ({"started_at": "2026-11-10T15:30:00"}, 422, "validation_error"),
        ({"started_at": 1731580325}, 422, "validation_error"),
        ({"config": {"timeout_ms": 0}}, 422, "validation_error"),
        ({"config": {"expected_steps": "web_search"}}, 422, "validation_error"),
        ({"tags": "demo"}, 422, "validation_error"),
    ],
)
def test_create_execution_rejects_bad_input(
    db_client: TestClient, db_session: Session, auth: dict, patch: dict, status: int, code: str
) -> None:
    agent = make_agent(db_session)
    response = db_client.post(
        "/api/v1/executions", json={"agent_id": agent.id, "input": {}, "config": {}, **patch}, headers=auth
    )
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert db_client.get("/api/v1/executions").json()["total"] == 0


def test_create_execution_requires_the_api_key(db_client: TestClient, db_session: Session) -> None:
    agent = make_agent(db_session)
    response = db_client.post("/api/v1/executions", json={"agent_id": agent.id, "input": {}, "config": {}})
    assert response.status_code == 401


def test_get_execution_detail(db_client: TestClient, db_session: Session) -> None:
    agent = make_agent(db_session, name="Invoice Processor")
    error = {"type": "KeyError", "message": "'results'", "stacktrace": None}
    execution = make_execution(
        db_session,
        agent,
        status="failed",
        ended_at=T0 + timedelta(seconds=2, milliseconds=500),
        duration_ms=2500,
        input={"invoice": 17},
        output=None,
        config={"model": "m"},
        error=error,
        tokens_input=1200,
        tokens_output=None,
        cost_usd=Decimal("0.012300"),
        step_count=4,
        tags=["seed"],
    )
    make_anomaly(db_session, execution)
    make_investigation(db_session, execution)

    response = db_client.get(f"/api/v1/executions/{execution.id}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == DETAIL_KEYS
    assert body["started_at"] == "2026-11-14T10:00:00.000Z"
    assert body["ended_at"] == "2026-11-14T10:00:02.500Z"
    assert (body["duration_ms"], body["step_count"], body["agent_name"]) == (2500, 4, "Invoice Processor")
    assert (body["tokens_input"], body["tokens_output"], body["tokens_total"]) == (1200, None, 1200)
    assert body["cost_usd"] == pytest.approx(0.0123)
    assert body["error"] == error
    assert (body["anomaly_count"], body["has_investigation"]) == (1, True)
    assert body["config"] == {"model": "m", "params": {}, "expected_steps": None, "timeout_ms": None}


@pytest.mark.parametrize("execution_id", ["exe_" + "0" * 32, "nope"])
def test_get_unknown_execution_is_not_found(
    db_client: TestClient, db_session: Session, execution_id: str
) -> None:
    response = db_client.get(f"/api/v1/executions/{execution_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.fixture
def seeded(db_session: Session) -> dict[str, Execution]:
    """Five executions across two agents, started one minute apart (a is oldest)."""
    research = make_agent(db_session, slug="research-assistant", name="Research Assistant")
    invoice = make_agent(db_session, slug="invoice-processor", name="Invoice Processor")
    a = make_execution(
        db_session,
        research,
        status="completed",
        started_at=T0,
        duration_ms=1000,
        tokens_input=100,
        tokens_output=50,
        cost_usd=Decimal("0.02"),
    )
    b = make_execution(
        db_session,
        research,
        status="failed",
        started_at=T0 + MINUTE,
        duration_ms=5000,
        tokens_input=900,
        cost_usd=Decimal("0.09"),
    )
    c = make_execution(db_session, invoice, status="completed", started_at=T0 + 2 * MINUTE, duration_ms=200)
    d = make_execution(
        db_session, invoice, status="timed_out", started_at=T0 + 3 * MINUTE, duration_ms=300000
    )
    e = make_execution(db_session, research, status="running", started_at=T0 + 4 * MINUTE, replay_of=b.id)
    make_anomaly(db_session, b)
    make_anomaly(db_session, c, type="ghost_completion", severity="critical")
    return {"a": a, "b": b, "c": c, "d": d, "e": e, "research": research, "invoice": invoice}


def listed(client: TestClient, seeded: dict, query: str = "") -> str:
    """The seeded executions a query returns, as their letters in response order."""
    response = client.get(f"/api/v1/executions{query}")
    assert response.status_code == 200, response.text
    page = response.json()
    letters = {seeded[letter].id: letter for letter in "abcde"}
    assert all(set(item) == SUMMARY_KEYS for item in page["items"])
    return "".join(letters[item["id"]] for item in page["items"])


def test_list_defaults_to_newest_first(db_client: TestClient, seeded: dict) -> None:
    page = db_client.get("/api/v1/executions").json()
    assert set(page) == {"items", "total", "limit", "offset"}
    assert (page["total"], page["limit"], page["offset"]) == (5, 50, 0)
    assert listed(db_client, seeded) == "edcba"


def test_list_filters(db_client: TestClient, seeded: dict) -> None:
    research, b = seeded["research"], seeded["b"]
    assert listed(db_client, seeded, f"?agent_id={research.id}") == "eba"
    assert listed(db_client, seeded, "?status=failed") == "b"
    assert listed(db_client, seeded, "?status=failed,timed_out,running") == "edb"
    assert listed(db_client, seeded, "?started_after=2026-11-14T10:02:00Z") == "edc"  # inclusive
    assert listed(db_client, seeded, "?started_before=2026-11-14T10:02:00Z") == "ba"  # exclusive
    assert (
        listed(
            db_client,
            seeded,
            "?started_after=2026-11-14T15:31:00%2B05:30&started_before=2026-11-14T10:03:00Z",
        )
        == "cb"
    )
    assert listed(db_client, seeded, "?min_duration_ms=1000") == "dba"  # running has no duration
    assert listed(db_client, seeded, "?max_duration_ms=1000") == "ca"
    assert listed(db_client, seeded, "?min_duration_ms=300&max_duration_ms=5000") == "ba"
    assert listed(db_client, seeded, "?has_anomaly=true") == "cb"
    assert listed(db_client, seeded, "?has_anomaly=false") == "eda"
    assert listed(db_client, seeded, "?is_replay=true") == "e"
    assert listed(db_client, seeded, "?is_replay=false") == "dcba"
    assert listed(db_client, seeded, f"?replay_of={b.id}") == "e"
    assert listed(db_client, seeded, "?q=invoice") == "dc"
    assert listed(db_client, seeded, f"?q={b.id[:12]}") == "b"
    assert listed(db_client, seeded, "?q=exe_") == "edcba"
    assert listed(db_client, seeded, "?q=zzz") == ""


def test_list_combines_filters(db_client: TestClient, seeded: dict) -> None:
    research = seeded["research"]
    assert (
        listed(db_client, seeded, f"?agent_id={research.id}&status=completed,failed&has_anomaly=true") == "b"
    )
    assert listed(db_client, seeded, f"?agent_id={research.id}&status=timed_out") == ""
    assert listed(db_client, seeded, "?q=research&is_replay=false&max_duration_ms=2000") == "a"


def test_list_sorting_puts_unknown_values_last(db_client: TestClient, seeded: dict) -> None:
    assert listed(db_client, seeded, "?sort=started_at") == "abcde"
    assert listed(db_client, seeded, "?sort=-started_at") == "edcba"
    assert listed(db_client, seeded, "?sort=duration_ms") == "cabde"
    assert listed(db_client, seeded, "?sort=-duration_ms") == "dbace"
    # tokens_total: a = 150, b = 900; c, d, e unknown (ties broken by id).
    assert listed(db_client, seeded, "?sort=tokens_total")[:2] == "ab"
    assert listed(db_client, seeded, "?sort=-tokens_total")[:2] == "ba"
    assert listed(db_client, seeded, "?sort=cost_usd")[:2] == "ab"
    assert listed(db_client, seeded, "?sort=-cost_usd")[:2] == "ba"


def test_list_pagination_reports_the_filtered_total(db_client: TestClient, seeded: dict) -> None:
    first = db_client.get("/api/v1/executions?limit=2").json()
    assert (len(first["items"]), first["total"], first["limit"], first["offset"]) == (2, 5, 2, 0)
    assert listed(db_client, seeded, "?limit=2&offset=2") == "cb"
    assert listed(db_client, seeded, "?limit=2&offset=4") == "a"
    beyond = db_client.get("/api/v1/executions?offset=50").json()
    assert (beyond["items"], beyond["total"]) == ([], 5)
    filtered = db_client.get("/api/v1/executions?status=completed&limit=1").json()
    assert (len(filtered["items"]), filtered["total"]) == (1, 2)


def test_list_summary_values(db_client: TestClient, seeded: dict) -> None:
    items = {item["id"]: item for item in db_client.get("/api/v1/executions").json()["items"]}
    a, b, e = (items[seeded[letter].id] for letter in "abe")
    assert (a["tokens_total"], b["tokens_total"], e["tokens_total"]) == (150, 900, None)
    assert a["cost_usd"] == pytest.approx(0.02) and e["cost_usd"] is None
    assert (a["anomaly_count"], b["anomaly_count"]) == (0, 1)
    assert e["replay_of"] == seeded["b"].id
    assert a["agent_name"] == "Research Assistant"


@pytest.mark.parametrize(
    ("query", "status", "code"),
    [
        ("?status=done", 422, "validation_error"),
        ("?status=", 422, "validation_error"),
        ("?sort=step_count", 400, "bad_request"),
        ("?sort=--started_at", 400, "bad_request"),
        ("?has_anomaly=maybe", 422, "validation_error"),
        ("?min_duration_ms=-1", 422, "validation_error"),
        ("?started_after=yesterday", 422, "validation_error"),
        ("?started_after=2026-11-14T10:00:00", 422, "validation_error"),
        ("?limit=500", 422, "validation_error"),
    ],
)
def test_list_rejects_bad_parameters(
    db_client: TestClient, db_session: Session, query: str, status: int, code: str
) -> None:
    response = db_client.get(f"/api/v1/executions{query}")
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
