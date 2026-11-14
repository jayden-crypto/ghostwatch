"""Contract §3: Agents."""

import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.agents import compute_health
from tests.factories import T0, make_agent, make_anomaly, make_execution, make_investigation

AGENT_KEYS = {"id", "name", "slug", "description", "framework", "metadata", "created_at", "stats"}
STATS_KEYS = {
    "total_executions",
    "completed",
    "failed",
    "timed_out",
    "running",
    "success_rate",
    "avg_duration_ms",
    "open_anomalies",
    "last_execution",
    "health",
}
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
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")
RESEARCH = {"name": "Research Assistant", "slug": "research-assistant"}


@pytest.mark.parametrize(
    ("total", "rate", "critical", "high", "expected"),
    [
        (0, None, False, False, "idle"),
        (0, None, True, True, "idle"),
        (3, None, False, False, "healthy"),  # only running executions: no terminal rate yet
        (10, 1.0, False, False, "healthy"),
        (10, 0.9, False, False, "healthy"),  # the degraded threshold is strict: < 0.9
        (10, 0.89, False, False, "degraded"),
        (10, 0.5, False, False, "degraded"),  # the failing threshold is strict: < 0.5
        (10, 0.49, False, False, "failing"),
        (10, 0.0, False, False, "failing"),
        (10, 1.0, False, True, "degraded"),
        (10, 1.0, True, False, "failing"),
        (10, 1.0, True, True, "failing"),
        (10, 0.4, False, True, "failing"),
    ],
)
def test_compute_health(total: int, rate: float | None, critical: bool, high: bool, expected: str) -> None:
    assert compute_health(total, rate, open_critical=critical, open_high=high) == expected


def test_register_creates_an_idle_agent(db_client: TestClient, auth: dict) -> None:
    response = db_client.post(
        "/api/v1/agents",
        json={**RESEARCH, "framework": "custom", "metadata": {"team": "search"}},
        headers=auth,
    )
    assert response.status_code == 201
    agent = response.json()
    assert set(agent) == AGENT_KEYS
    assert set(agent["stats"]) == STATS_KEYS
    assert re.fullmatch(r"agt_[0-9a-f]{32}", agent["id"])
    assert TIMESTAMP.fullmatch(agent["created_at"])
    assert (agent["name"], agent["slug"], agent["framework"]) == (
        "Research Assistant",
        "research-assistant",
        "custom",
    )
    assert agent["description"] is None
    assert agent["metadata"] == {"team": "search"}
    assert agent["stats"] == {
        "total_executions": 0,
        "completed": 0,
        "failed": 0,
        "timed_out": 0,
        "running": 0,
        "success_rate": None,
        "avg_duration_ms": None,
        "open_anomalies": 0,
        "last_execution": None,
        "health": "idle",
    }


def test_register_again_updates_and_returns_200(db_client: TestClient, auth: dict) -> None:
    first = db_client.post("/api/v1/agents", json={**RESEARCH, "description": "Finds things"}, headers=auth)
    second = db_client.post(
        "/api/v1/agents", json={**RESEARCH, "name": "Research Assistant v2"}, headers=auth
    )
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["created_at"] == first.json()["created_at"]
    assert second.json()["name"] == "Research Assistant v2"
    assert second.json()["description"] == "Finds things"  # not sent, so not changed

    cleared = db_client.post("/api/v1/agents", json={**RESEARCH, "description": None}, headers=auth)
    assert cleared.json()["description"] is None
    assert db_client.get("/api/v1/agents").json()["total"] == 1


def test_register_requires_the_api_key(db_client: TestClient) -> None:
    response = db_client.post("/api/v1/agents", json=RESEARCH)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert db_client.get("/api/v1/agents").json()["total"] == 0


@pytest.mark.parametrize("slug", ["Research Assistant", "UPPER", "under_score", "", "café"])
def test_register_rejects_bad_slugs(db_client: TestClient, auth: dict, slug: str) -> None:
    response = db_client.post("/api/v1/agents", json={"name": "X", "slug": slug}, headers=auth)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["body", "slug"]


def test_register_rejects_unknown_fields(db_client: TestClient, auth: dict) -> None:
    response = db_client.post("/api/v1/agents", json={**RESEARCH, "colour": "blue"}, headers=auth)
    assert response.status_code == 422


def test_get_agent(db_client: TestClient, db_session: Session) -> None:
    agent = make_agent(db_session, slug="support-triage", name="Support Triage")
    response = db_client.get(f"/api/v1/agents/{agent.id}")
    assert response.status_code == 200
    assert response.json()["slug"] == "support-triage"


@pytest.mark.parametrize("agent_id", ["agt_" + "0" * 32, "not-an-id"])
def test_get_unknown_agent_is_not_found(db_client: TestClient, db_session: Session, agent_id: str) -> None:
    response = db_client.get(f"/api/v1/agents/{agent_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert agent_id in response.json()["error"]["message"]


def test_stats_are_computed_from_stored_rows(db_client: TestClient, db_session: Session) -> None:
    agent = make_agent(db_session)
    other = make_agent(db_session)
    minute = timedelta(minutes=1)
    for index, duration in enumerate((100, 200, 300)):
        make_execution(
            db_session, agent, status="completed", started_at=T0 + index * minute, duration_ms=duration
        )
    make_execution(db_session, agent, status="failed", started_at=T0 + 3 * minute, duration_ms=400)
    make_execution(db_session, agent, status="timed_out", started_at=T0 + 4 * minute, duration_ms=1000)
    latest = make_execution(db_session, agent, status="running", started_at=T0 + 5 * minute)
    make_anomaly(db_session, latest, severity="medium")
    make_anomaly(db_session, latest, type="duration_spike", severity="medium", status="resolved")
    make_investigation(db_session, latest)
    make_execution(db_session, other, status="failed", started_at=T0 + 9 * minute, duration_ms=9999)

    stats = db_client.get(f"/api/v1/agents/{agent.id}").json()["stats"]
    assert stats["total_executions"] == 6
    assert (stats["completed"], stats["failed"], stats["timed_out"], stats["running"]) == (3, 1, 1, 1)
    assert stats["success_rate"] == pytest.approx(0.6)
    assert stats["avg_duration_ms"] == 400  # (100 + 200 + 300 + 400 + 1000) / 5 terminal executions
    assert stats["open_anomalies"] == 1
    assert stats["health"] == "degraded"
    last = stats["last_execution"]
    assert set(last) == SUMMARY_KEYS
    assert last["id"] == latest.id
    assert (last["status"], last["agent_name"], last["duration_ms"]) == ("running", agent.name, None)
    assert (last["anomaly_count"], last["has_investigation"]) == (2, True)
    assert (last["tokens_total"], last["cost_usd"], last["error"], last["replay_of"]) == (
        None,
        None,
        None,
        None,
    )


def test_health_uses_only_the_last_20_terminal_executions(db_client: TestClient, db_session: Session) -> None:
    recovered = make_agent(db_session, slug="recovered")
    regressed = make_agent(db_session, slug="regressed")
    minute = timedelta(minutes=1)
    for index in range(30):
        # recovered: 10 old failures then 20 successes. regressed: 10 old successes then 20 failures.
        old = index < 10
        make_execution(
            db_session, recovered, status="failed" if old else "completed", started_at=T0 + index * minute
        )
        make_execution(
            db_session, regressed, status="completed" if old else "failed", started_at=T0 + index * minute
        )
    # A running execution is newer than all of them but is not terminal, so it does not use a slot.
    make_execution(db_session, recovered, status="running", started_at=T0 + 60 * minute)

    recovered_stats = db_client.get(f"/api/v1/agents/{recovered.id}").json()["stats"]
    assert recovered_stats["success_rate"] == pytest.approx(20 / 30)  # all-time
    assert recovered_stats["health"] == "healthy"  # last 20 terminal: 100 %

    regressed_stats = db_client.get(f"/api/v1/agents/{regressed.id}").json()["stats"]
    assert regressed_stats["success_rate"] == pytest.approx(10 / 30)
    assert regressed_stats["health"] == "failing"


def test_open_anomalies_drive_health(db_client: TestClient, db_session: Session) -> None:
    agent = make_agent(db_session)
    execution = make_execution(db_session, agent, status="completed", duration_ms=10)
    assert db_client.get(f"/api/v1/agents/{agent.id}").json()["stats"]["health"] == "healthy"

    high = make_anomaly(db_session, execution, type="repeated_tool_failure", severity="high")
    assert db_client.get(f"/api/v1/agents/{agent.id}").json()["stats"]["health"] == "degraded"

    critical = make_anomaly(db_session, execution, type="ghost_completion", severity="critical")
    assert db_client.get(f"/api/v1/agents/{agent.id}").json()["stats"]["health"] == "failing"

    critical.status = "acknowledged"
    high.status = "resolved"
    db_session.flush()
    stats = db_client.get(f"/api/v1/agents/{agent.id}").json()["stats"]
    assert (stats["health"], stats["open_anomalies"]) == ("healthy", 0)


def test_list_agents_sorts_searches_and_paginates(db_client: TestClient, db_session: Session) -> None:
    make_agent(db_session, slug="support-triage", name="Support Triage", created_at=T0)
    make_agent(db_session, slug="invoice-processor", name="Invoice Processor", created_at=T0 + timedelta(1))
    make_agent(db_session, slug="research-assistant", name="Research Assistant", created_at=T0 + timedelta(2))

    def names(query: str = "") -> list[str]:
        response = db_client.get(f"/api/v1/agents{query}")
        assert response.status_code == 200, response.text
        return [agent["name"] for agent in response.json()["items"]]

    page = db_client.get("/api/v1/agents").json()
    assert set(page) == {"items", "total", "limit", "offset"}
    assert (page["total"], page["limit"], page["offset"]) == (3, 50, 0)
    assert names() == ["Invoice Processor", "Research Assistant", "Support Triage"]
    assert names("?sort=-name") == ["Support Triage", "Research Assistant", "Invoice Processor"]
    assert names("?sort=-created_at") == ["Research Assistant", "Invoice Processor", "Support Triage"]
    assert names("?q=ASSIST") == ["Research Assistant"]
    assert names("?q=invoice-proc") == ["Invoice Processor"]
    assert names("?q=%25") == []  # a literal percent sign is not a wildcard

    second = db_client.get("/api/v1/agents?limit=2&offset=2").json()
    assert [agent["name"] for agent in second["items"]] == ["Support Triage"]
    assert (second["total"], second["limit"], second["offset"]) == (3, 2, 2)


def test_list_agents_filters_by_health(db_client: TestClient, db_session: Session) -> None:
    make_agent(db_session, slug="idle-one", name="Idle")
    healthy = make_agent(db_session, slug="healthy-one", name="Healthy")
    failing = make_agent(db_session, slug="failing-one", name="Failing")
    make_execution(db_session, healthy, status="completed")
    make_execution(db_session, failing, status="failed")

    def slugs(health: str) -> set[str]:
        page = db_client.get(f"/api/v1/agents?health={health}").json()
        assert page["total"] == len(page["items"])
        return {agent["slug"] for agent in page["items"]}

    assert slugs("idle") == {"idle-one"}
    assert slugs("healthy") == {"healthy-one"}
    assert slugs("failing") == {"failing-one"}
    assert slugs("degraded") == set()
    assert slugs("idle,failing") == {"idle-one", "failing-one"}


@pytest.mark.parametrize(
    ("query", "status", "code"),
    [
        ("?health=great", 422, "validation_error"),
        ("?sort=slug", 400, "bad_request"),
        ("?limit=201", 422, "validation_error"),
        ("?limit=0", 422, "validation_error"),
        ("?offset=-1", 422, "validation_error"),
    ],
)
def test_list_agents_rejects_bad_parameters(
    db_client: TestClient, db_session: Session, query: str, status: int, code: str
) -> None:
    response = db_client.get(f"/api/v1/agents{query}")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_empty_list_is_a_valid_page(db_client: TestClient, db_session: Session) -> None:
    assert db_client.get("/api/v1/agents").json() == {"items": [], "total": 0, "limit": 50, "offset": 0}
