"""Smoke test against a running backend over real HTTP.

Usage (from backend/, with the server running):  uv run python -m scripts.smoke [base_url]

It registers an agent called "Smoke Test", runs one execution through ingestion, then reads it back
through every implemented endpoint, validating each response body against the contract schemas as
strict JSON. Exits non-zero on the first mismatch. It writes real rows to the server's database.
"""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
from pydantic import TypeAdapter, ValidationError

from app.config import get_settings
from app.schemas.agents import Agent
from app.schemas.anomalies import Anomaly
from app.schemas.common import ErrorEnvelope, Page
from app.schemas.events import IngestResponse, StoredEvent
from app.schemas.executions import ExecutionDetail, ExecutionSummary
from app.schemas.health import Health
from app.schemas.stats import StatsOverview, StatsTimeseries
from app.schemas.traces import Trace
from app.timeutil import format_timestamp

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api/v1"
AUTH = {"Authorization": f"Bearer {get_settings().ghostwatch_api_key}"}
ORIGIN = "http://localhost:3000"
client = httpx2.Client(base_url=BASE_URL, timeout=10, headers={"Origin": ORIGIN})
failures = 0


def check(label: str, response: httpx2.Response, status: int, schema: Any) -> Any:
    """Assert the status code, validate the body against the schema and print one line."""
    global failures
    problem = None
    parsed = None
    if response.status_code != status:
        problem = f"expected {status}, got {response.status_code}: {response.text[:200]}"
    else:
        try:
            parsed = TypeAdapter(schema).validate_json(response.content, strict=True)
        except ValidationError as exc:
            problem = f"body does not match the contract: {exc}"
    if response.headers.get("access-control-allow-origin") != ORIGIN:
        problem = problem or "missing CORS header for http://localhost:3000"
    print(f"{'FAIL' if problem else 'ok  '} {response.status_code} {label}")
    if problem:
        failures += 1
        print(f"     {problem}")
    return parsed


def step_id() -> str:
    return f"stp_{uuid.uuid4().hex}"


def main() -> int:
    health = check("GET /health", client.get("/health"), 200, Health)
    if health is None or health.database != "ok":
        print("     database is not ok; start Postgres and run migrations first")
        return 1

    body = {"name": "Smoke Test", "slug": "smoke-test", "framework": "custom"}
    check("POST /agents without a key", client.post("/agents", json=body), 401, ErrorEnvelope)
    first = client.post("/agents", json=body, headers=AUTH)
    agent = check("POST /agents", first, first.status_code if first.status_code in (200, 201) else 201, Agent)
    check("POST /agents again (upsert)", client.post("/agents", json=body, headers=AUTH), 200, Agent)

    started_at = datetime.now(UTC) - timedelta(seconds=5)

    def at(offset_ms: int) -> str:
        return format_timestamp(started_at + timedelta(milliseconds=offset_ms))

    created = client.post(
        "/executions",
        json={
            "agent_id": agent.id,
            "input": {"question": "Does it work over real HTTP?"},
            "config": {"model": "claude-fable-5-2", "expected_steps": ["web_search", "parse_results"]},
            "tags": ["smoke"],
            "started_at": at(0),
        },
        headers=AUTH,
    )
    execution = check("POST /executions", created, 201, ExecutionDetail)
    events_url = f"/executions/{execution.id}/events"

    plan, search_1, search_2, parse = step_id(), step_id(), step_id(), step_id()
    first_batch = [
        {
            "seq": 1,
            "type": "step.started",
            "timestamp": at(10),
            "payload": {"step_id": plan, "name": "plan", "step_type": "reasoning", "input": {"q": "x"}},
        },
        {
            "seq": 2,
            "type": "step.completed",
            "timestamp": at(110),
            "payload": {"step_id": plan, "output": {"queries": ["x"]}},
        },
        {
            "seq": 3,
            "type": "step.started",
            "timestamp": at(120),
            "payload": {
                "step_id": search_1,
                "name": "web_search",
                "step_type": "tool_call",
                "tool_name": "web_search",
            },
        },
        {
            "seq": 4,
            "type": "step.failed",
            "timestamp": at(420),
            "payload": {
                "step_id": search_1,
                "error": {"type": "HTTPError", "message": "429 Too Many Requests"},
                "output": {"status": 429},
            },
        },
    ]
    ingested = check(
        "POST events (batch 1)",
        client.post(events_url, json={"events": first_batch}, headers=AUTH),
        202,
        IngestResponse,
    )
    assert (ingested.accepted, ingested.duplicates, ingested.execution_status) == (4, 0, "running"), ingested

    running = check("GET trace while running", client.get(f"/executions/{execution.id}/trace"), 200, Trace)
    assert (running.execution.status, len(running.steps), running.event_count) == ("running", 2, 4), running

    second_batch = [
        {
            "seq": 8,
            "type": "step.failed",
            "timestamp": at(1020),
            "payload": {
                "step_id": parse,
                "error": {
                    "type": "KeyError",
                    "message": "'results'",
                    "stacktrace": "Traceback (most recent call last):\n  ...\nKeyError: 'results'",
                },
            },
        },
        {
            "seq": 5,
            "type": "step.started",
            "timestamp": at(500),
            "payload": {
                "step_id": search_2,
                "name": "web_search",
                "step_type": "tool_call",
                "tool_name": "web_search",
                "attempt": 2,
            },
        },
        {
            "seq": 7,
            "type": "step.started",
            "timestamp": at(1000),
            "payload": {
                "step_id": parse,
                "name": "parse_results",
                "step_type": "reasoning",
                "parent_step_id": search_2,
            },
        },
        {
            "seq": 6,
            "type": "step.completed",
            "timestamp": at(990),
            "payload": {
                "step_id": search_2,
                "output": {"data": ["y" * 100] * 1000, "meta": {}},
                "tokens_input": 900,
                "tokens_output": 120,
            },
        },
        {
            "seq": 9,
            "type": "log",
            "timestamp": at(1021),
            "payload": {"level": "error", "message": "giving up"},
        },
        {
            "seq": 10,
            "type": "execution.failed",
            "timestamp": at(1030),
            "payload": {"error": {"type": "KeyError", "message": "'results'"}},
        },
    ]
    ingested = check(
        "POST events (batch 2, out of order, terminal)",
        client.post(events_url, json={"events": second_batch}, headers=AUTH),
        202,
        IngestResponse,
    )
    assert (ingested.accepted, ingested.duplicates, ingested.execution_status) == (6, 0, "failed"), ingested
    retried = check(
        "POST events (retry of batch 2)",
        client.post(events_url, json={"events": second_batch}, headers=AUTH),
        202,
        IngestResponse,
    )
    assert (retried.accepted, retried.duplicates) == (0, 6), retried

    late = [
        {
            "seq": 11,
            "type": "step.started",
            "timestamp": at(2000),
            "payload": {"step_id": step_id(), "name": "late", "step_type": "custom"},
        }
    ]
    check(
        "POST events after terminal",
        client.post(events_url, json={"events": late}, headers=AUTH),
        409,
        ErrorEnvelope,
    )
    check(
        "POST events with a bad body",
        client.post(events_url, json={"events": []}, headers=AUTH),
        422,
        ErrorEnvelope,
    )

    detail = check("GET /executions/{id}", client.get(f"/executions/{execution.id}"), 200, ExecutionDetail)
    assert (detail.status, detail.duration_ms, detail.step_count) == ("failed", 1030, 4), detail
    assert (detail.tokens_input, detail.tokens_output, detail.tokens_total, detail.cost_usd) == (
        900,
        120,
        1020,
        None,
    ), detail
    assert detail.error.type == "KeyError", detail.error

    trace = check("GET /executions/{id}/trace", client.get(f"/executions/{execution.id}/trace"), 200, Trace)
    assert [step.name for step in trace.steps] == ["plan", "web_search", "web_search", "parse_results"], (
        trace.steps
    )
    assert [step.depth for step in trace.steps] == [0, 0, 0, 1]
    assert [step.offset_ms for step in trace.steps] == [10, 120, 500, 1000]
    assert [step.duration_ms for step in trace.steps] == [100, 300, 490, 20]
    assert [step.status for step in trace.steps] == ["completed", "failed", "completed", "failed"]
    assert [step.attempt for step in trace.steps] == [1, 1, 2, 1]
    assert trace.steps[2].output["_truncated"] is True and trace.event_count == 10

    events = check("GET /executions/{id}/events", client.get(events_url), 200, Page[StoredEvent])
    assert [event.seq for event in events.items] == list(range(1, 11)), [event.seq for event in events.items]
    paged = check(
        "GET events?limit=3&offset=8",
        client.get(events_url, params={"limit": 3, "offset": 8}),
        200,
        Page[StoredEvent],
    )
    assert ([event.seq for event in paged.items], paged.total) == ([9, 10], 10)

    listed = check(
        "GET /executions (filtered, sorted)",
        client.get(
            "/executions",
            params={
                "agent_id": agent.id,
                "status": "failed,timed_out",
                "sort": "-started_at",
                "q": "smoke",
                "limit": 5,
            },
        ),
        200,
        Page[ExecutionSummary],
    )
    assert listed.items[0].id == execution.id, listed.items[:1]
    check(
        "GET /executions?has_anomaly=true",
        client.get("/executions", params={"has_anomaly": "true"}),
        200,
        Page[ExecutionSummary],
    )
    after = check(
        "GET /executions?started_after=<now>",
        client.get("/executions", params={"started_after": format_timestamp(datetime.now(UTC))}),
        200,
        Page[ExecutionSummary],
    )
    assert after.total == 0, after.total

    agents = check("GET /agents?q=smoke", client.get("/agents", params={"q": "smoke"}), 200, Page[Agent])
    stats = agents.items[0].stats
    assert (
        stats.last_execution is not None and stats.failed >= 1 and stats.health in ("failing", "degraded")
    ), stats
    check("GET /agents/{id}", client.get(f"/agents/{agent.id}"), 200, Agent)

    overview = check(
        "GET /stats/overview?window=24h",
        client.get("/stats/overview", params={"window": "24h"}),
        200,
        StatsOverview,
    )
    series = check(
        "GET /stats/timeseries?window=24h",
        client.get("/stats/timeseries", params={"window": "24h"}),
        200,
        StatsTimeseries,
    )
    assert len(series.points) == 24 and sum(point.failed for point in series.points) == overview.failed, (
        overview,
        len(series.points),
    )
    assert (
        series.points[-1].failed >= 1 or series.points[-2].failed >= 1
    )  # this run, in the current or previous hour
    week = check(
        "GET /stats/timeseries?agent_id=",
        client.get("/stats/timeseries", params={"agent_id": agent.id}),
        200,
        StatsTimeseries,
    )
    assert (week.bucket, len(week.points)) == ("day", 7)

    anomalies = check(
        "GET /anomalies?execution_id=",
        client.get("/anomalies", params={"execution_id": execution.id}),
        200,
        Page[Anomaly],
    )
    assert all(anomaly.execution_id == execution.id and anomaly.evidence for anomaly in anomalies.items)
    assert len(anomalies.items) == detail.anomaly_count, (len(anomalies.items), detail.anomaly_count)

    check(
        "GET unknown execution",
        client.get("/executions/exe_00000000000000000000000000000000/trace"),
        404,
        ErrorEnvelope,
    )
    check("GET unknown route", client.get("/nothing-here"), 404, ErrorEnvelope)
    check("GET /executions?sort=nope", client.get("/executions", params={"sort": "nope"}), 400, ErrorEnvelope)
    check(
        "GET /executions?status=nope",
        client.get("/executions", params={"status": "nope"}),
        422,
        ErrorEnvelope,
    )

    print(f"\n{'FAILED' if failures else 'PASSED'}: execution {execution.id}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
