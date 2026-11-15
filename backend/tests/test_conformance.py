"""Contract conformance.

Three layers, all using the same strict schemas:
1. The schemas themselves reject drift: a missing key, an extra key, a wrong type, a bad id, a
   timestamp that is not UTC-milliseconds-Z, an unknown enum value.
2. Every response the running API produces validates against them.
3. Every file in contract/fixtures/ validates against them.

Because the schemas forbid extra keys and require every key, a fixture and a live response that
both validate have identical key sets, except inside the fields the contract types as free-form JSON.
"""

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.models import Execution
from app.schemas.agents import Agent
from app.schemas.anomalies import Anomaly
from app.schemas.common import ErrorEnvelope, Page
from app.schemas.events import IngestResponse, StoredEvent
from app.schemas.executions import ExecutionDetail, ExecutionSummary
from app.schemas.health import Health
from app.schemas.investigations import Investigation
from app.schemas.replays import Replay, ReplayClaim
from app.schemas.stats import StatsOverview, StatsTimeseries
from app.schemas.traces import Trace
from tests import contract_examples as examples
from tests import events as ev
from tests.events import new_step_id, post_events
from tests.factories import make_anomaly
from tests.fixture_map import schema_for

FIXTURE_DIR = REPO_ROOT / "contract" / "fixtures"
FIXTURES = sorted(FIXTURE_DIR.glob("*.json")) if FIXTURE_DIR.is_dir() else []

# Contract §3-§11 plus the error envelope: each needs at least one fixture.
FIXTURE_RESOURCES = {
    "agents",
    "executions",
    "stats",
    "anomalies",
    "investigations",
    "replays",
    "health",
    "error",
}

# Keys whose values the contract types as arbitrary JSON or a free-form object.
FREE_FORM = {"metadata", "input", "output", "payload", "params", "observed", "expected", "details"}


def validate(schema: Any, document: Any) -> Any:
    """Validate the way a client would see it: as JSON text, with no type coercion."""
    text = document if isinstance(document, str | bytes) else json.dumps(document)
    return TypeAdapter(schema).validate_json(text, strict=True)


def is_valid(schema: Any, document: Any) -> bool:
    try:
        validate(schema, document)
    except ValidationError:
        return False
    return True


def dict_paths(node: Any, path: tuple = ()) -> Iterator[tuple]:
    """Path to every JSON object inside `node` that the contract gives a fixed shape."""
    if isinstance(node, dict):
        yield path
        for key, value in node.items():
            if key not in FREE_FORM:
                yield from dict_paths(value, (*path, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from dict_paths(value, (*path, index))


def at_path(document: Any, path: tuple) -> Any:
    for part in path:
        document = document[part]
    return document


EXAMPLE_IDS = [name for name, _, _ in examples.EXAMPLES]


@pytest.mark.parametrize(("name", "schema", "example"), examples.EXAMPLES, ids=EXAMPLE_IDS)
def test_examples_are_valid(name: str, schema: Any, example: dict) -> None:
    validate(schema, example)


@pytest.mark.parametrize(("name", "schema", "example"), examples.EXAMPLES, ids=EXAMPLE_IDS)
def test_every_key_is_required_even_when_nullable(name: str, schema: Any, example: dict) -> None:
    checked = 0
    for path in dict_paths(example):
        for key in at_path(example, path):
            mutated = copy.deepcopy(example)
            del at_path(mutated, path)[key]
            assert not is_valid(schema, mutated), f"{name}: removing {(*path, key)} still validated"
            checked += 1
    assert checked > 0


@pytest.mark.parametrize(("name", "schema", "example"), examples.EXAMPLES, ids=EXAMPLE_IDS)
def test_unknown_keys_are_rejected(name: str, schema: Any, example: dict) -> None:
    for path in dict_paths(example):
        if path and path[-1] == "config":
            continue  # ExecutionConfig allows free-form extras by contract
        mutated = copy.deepcopy(example)
        at_path(mutated, path)["unexpected_key"] = 1
        assert not is_valid(schema, mutated), f"{name}: an extra key at {path} still validated"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "exe_3F9C2A7E1B4D4E0F9A8B7C6D5E4F3A2B"),  # uppercase hex
        ("id", "exe_123"),
        ("id", examples.AGENT_ID),  # wrong prefix for this field
        ("agent_id", "research-assistant"),
        ("replay_of", "exe_"),
        ("started_at", "2026-11-14T10:32:05Z"),  # no milliseconds
        ("started_at", "2026-11-14T10:32:05.123+00:00"),  # offset instead of Z
        ("started_at", "2026-11-14T10:32:05.123456Z"),  # microseconds
        ("started_at", "2026-11-14 10:32:05.123Z"),
        ("started_at", 1731580325),  # epoch number
        ("ended_at", "2026-11-14T16:02:05.123"),  # local time
        ("status", "success"),
        ("status", "COMPLETED"),
        ("duration_ms", "2500"),
        ("duration_ms", 2500.5),
        ("step_count", None),
        ("anomaly_count", True),
        ("has_investigation", 1),
        ("cost_usd", "0.01"),
        ("error", "KeyError: 'results'"),
        ("error", {"type": "KeyError", "message": "'results'"}),  # stacktrace missing
        ("agent_name", None),
    ],
)
def test_execution_summary_rejects_wrong_values(field: str, value: Any) -> None:
    assert is_valid(ExecutionSummary, examples.SUMMARY)
    assert not is_valid(ExecutionSummary, {**examples.SUMMARY, field: value})


def test_unknown_values_of_every_enum_are_rejected() -> None:
    cases = [
        (Agent, examples.AGENT, ("stats", "health")),
        (Trace, examples.TRACE, ("steps", 0, "type")),
        (Trace, examples.TRACE, ("steps", 0, "status")),
        (Trace, examples.TRACE, ("anomalies", 0, "type")),
        (Trace, examples.TRACE, ("anomalies", 0, "severity")),
        (Trace, examples.TRACE, ("anomalies", 0, "status")),
        (Trace, examples.TRACE, ("anomalies", 0, "evidence", 0, "kind")),
        (Page[StoredEvent], examples.page(examples.STORED_EVENT), ("items", 0, "type")),
        (Investigation, examples.INVESTIGATION, ("status",)),
        (Investigation, examples.INVESTIGATION, ("trigger",)),
        (Investigation, examples.INVESTIGATION, ("provider",)),
        (Investigation, examples.INVESTIGATION, ("report", "root_cause", "status")),
        (Investigation, examples.INVESTIGATION, ("report", "hypotheses", 0, "confidence")),
        (Replay, examples.REPLAY, ("mode",)),
        (Replay, examples.REPLAY, ("status",)),
        (Replay, examples.REPLAY, ("comparison", "outcome")),
        (Replay, examples.REPLAY, ("comparison", "step_diffs", 0, "change")),
        (StatsOverview, examples.STATS_OVERVIEW, ("window",)),
        (StatsTimeseries, examples.STATS_TIMESERIES, ("bucket",)),
        (Health, examples.HEALTH, ("llm_provider",)),
        (ErrorEnvelope, examples.ERROR_ENVELOPE, ("error", "code")),
    ]
    for schema, example, path in cases:
        mutated = copy.deepcopy(example)
        at_path(mutated, path[:-1])[path[-1]] = "something_else"
        assert is_valid(schema, example), path
        assert not is_valid(schema, mutated), f"{schema.__name__}: unknown value at {path} still validated"


def test_anomalies_and_facts_need_evidence() -> None:
    assert not is_valid(Trace, {**examples.TRACE, "anomalies": [{**examples.ANOMALY, "evidence": []}]})
    assert not is_valid(Trace, {**examples.TRACE, "anomalies": [{**examples.ANOMALY, "title": "x" * 81}]})
    report = copy.deepcopy(examples.REPORT)
    report["facts"][0]["evidence"] = []
    assert not is_valid(Investigation, {**examples.INVESTIGATION, "report": report})


def investigation_with(**report_changes: Any) -> dict[str, Any]:
    return {**examples.INVESTIGATION, "report": {**copy.deepcopy(examples.REPORT), **report_changes}}


def test_investigation_reports_must_be_internally_consistent() -> None:
    hypothesis = examples.REPORT["hypotheses"][0]
    root_cause = examples.REPORT["root_cause"]
    broken = {
        "cites a missing fact": investigation_with(
            hypotheses=[{**hypothesis, "supporting_fact_ids": ["F1", "F9"]}]
        ),
        "contradicting fact missing": investigation_with(
            hypotheses=[{**hypothesis, "contradicting_fact_ids": ["F2"]}]
        ),
        "no supporting fact": investigation_with(hypotheses=[{**hypothesis, "supporting_fact_ids": []}]),
        "recommendation cites a missing hypothesis": investigation_with(
            recommendations=[{**examples.REPORT["recommendations"][0], "hypothesis_id": "H7"}]
        ),
        "root cause cites a missing hypothesis": investigation_with(
            root_cause={**root_cause, "hypothesis_id": "H7"}
        ),
        "confirmed without a signature": investigation_with(root_cause={**root_cause, "signature": None}),
        "probable with a signature": investigation_with(root_cause={**root_cause, "status": "probable"}),
        "insufficient evidence with a hypothesis": investigation_with(
            root_cause={**root_cause, "status": "insufficient_evidence", "signature": None}
        ),
        "duplicate fact ids": investigation_with(facts=[examples.REPORT["facts"][0]] * 2),
        "completed without a report": {**examples.INVESTIGATION, "report": None},
        "queued with a report": {**examples.INVESTIGATION, "status": "queued"},
    }
    assert is_valid(Investigation, examples.INVESTIGATION)
    for reason, document in broken.items():
        assert not is_valid(Investigation, document), reason

    assert is_valid(
        Investigation, investigation_with(root_cause={**root_cause, "status": "probable", "signature": None})
    )
    assert is_valid(
        Investigation,
        investigation_with(
            root_cause={
                "status": "insufficient_evidence",
                "statement": "Unknown.",
                "hypothesis_id": None,
                "signature": None,
            },
            hypotheses=[],
            recommendations=[],
        ),
    )
    assert is_valid(
        Investigation, {**examples.INVESTIGATION, "status": "running", "report": None, "completed_at": None}
    )


def test_a_live_replay_must_be_authorized() -> None:
    assert not is_valid(Replay, {**examples.REPLAY, "mode": "live", "side_effects_authorized": False})
    assert is_valid(Replay, {**examples.REPLAY, "mode": "live", "side_effects_authorized": True})


def test_live_responses_validate_against_the_contract(
    db_client: TestClient, db_session: Session, auth: dict
) -> None:
    """Drive every implemented endpoint and validate each raw response body."""
    client = db_client
    created = client.post(
        "/api/v1/agents", json={"name": "Research Assistant", "slug": "research-assistant"}, headers=auth
    )
    agent = validate(Agent, created.content)
    assert created.status_code == 201
    updated = client.post(
        "/api/v1/agents", json={"name": "Research Assistant", "slug": "research-assistant"}, headers=auth
    )
    assert updated.status_code == 200
    validate(Agent, updated.content)

    started = client.post(
        "/api/v1/executions",
        json={"agent_id": agent.id, "input": {"question": "q"}, "config": {"expected_steps": ["web_search"]}},
        headers=auth,
    )
    assert started.status_code == 201
    execution = validate(ExecutionDetail, started.content)

    search, parse = new_step_id(), new_step_id()
    ingested = post_events(
        client,
        auth,
        execution.id,
        [
            ev.step_started(
                1,
                search,
                10,
                name="web_search",
                step_type="tool_call",
                tool_name="web_search",
                input={"q": "q"},
            ),
            ev.step_completed(
                2, search, 310, output={"rows": ["x" * 100] * 1000}, tokens_input=10, tokens_output=5
            ),
            ev.step_started(3, parse, 320, name="parse_results", parent_step_id=search),
            ev.step_failed(4, parse, 330),
            ev.log(5, 331, message="giving up", level="error", step_id=parse),
            ev.execution_failed(6, 340),
        ],
    )
    assert ingested.status_code == 202
    assert validate(IngestResponse, ingested.content).execution_status == "failed"
    make_anomaly(db_session, db_session.get(Execution, execution.id))

    requested = client.post(
        f"/api/v1/executions/{execution.id}/replay", json={"mode": "sandbox", "note": "n"}
    )
    assert requested.status_code == 201
    replay = validate(Replay, requested.content)
    claimed = client.post(f"/api/v1/replays/{replay.id}/claim", headers=auth)
    assert claimed.status_code == 200
    assert len(validate(ReplayClaim, claimed.content).bundle.recorded_calls) == 1
    rerun = client.post(
        "/api/v1/executions",
        json={
            "agent_id": agent.id,
            "input": {},
            "config": {},
            "replay_of": execution.id,
            "replay_id": replay.id,
        },
        headers=auth,
    )
    rerun_step = new_step_id()
    post_events(
        client,
        auth,
        rerun.json()["id"],
        [
            ev.step_started(1, rerun_step, 0, name="web_search", metadata={"replay_source": "recorded"}),
            ev.step_completed(2, rerun_step, 5),
            ev.execution_completed(3, 10),
        ],
    )

    responses = {
        f"/api/v1/agents/{agent.id}": Agent,
        "/api/v1/agents": Page[Agent],
        "/api/v1/agents?health=failing&q=research": Page[Agent],
        f"/api/v1/executions/{execution.id}": ExecutionDetail,
        "/api/v1/executions": Page[ExecutionSummary],
        "/api/v1/executions?status=failed&has_anomaly=true&sort=-duration_ms": Page[ExecutionSummary],
        "/api/v1/executions?status=running": Page[ExecutionSummary],  # an empty page
        f"/api/v1/executions/{execution.id}/trace": Trace,
        f"/api/v1/executions/{execution.id}/events": Page[StoredEvent],
        f"/api/v1/investigations/{execution.id}": Investigation,
        "/api/v1/investigations": Page[Investigation],
        f"/api/v1/investigations?status=completed&agent_id={agent.id}": Page[Investigation],
        "/api/v1/investigations?status=failed": Page[Investigation],  # an empty page
        "/api/v1/anomalies": Page[Anomaly],
        f"/api/v1/anomalies?execution_id={execution.id}&severity=medium,high&status=open": Page[Anomaly],
        "/api/v1/anomalies?type=ghost_completion": Page[Anomaly],  # an empty page
        "/api/v1/stats/overview": StatsOverview,
        "/api/v1/stats/overview?window=24h": StatsOverview,
        "/api/v1/stats/timeseries": StatsTimeseries,
        f"/api/v1/stats/timeseries?window=30d&bucket=hour&agent_id={agent.id}": StatsTimeseries,
        f"/api/v1/replays/{replay.id}": Replay,  # completed, with its comparison
        "/api/v1/replays": Page[Replay],
        f"/api/v1/replays?status=completed&original_execution_id={execution.id}": Page[Replay],
        "/api/v1/replays?status=pending": Page[Replay],  # an empty page
        "/api/v1/health": Health,
    }
    for path, schema in responses.items():
        response = client.get(path)
        assert response.status_code == 200, f"{path}: {response.text}"
        try:
            validate(schema, response.content)
        except ValidationError as exc:
            pytest.fail(f"GET {path} does not match the contract:\n{exc}")

    trace = validate(Trace, client.get(f"/api/v1/executions/{execution.id}/trace").content)
    assert (len(trace.steps), len(trace.anomalies), trace.event_count) == (2, 1, 6)
    assert trace.steps[0].output["_truncated"] is True

    errors = [
        (client.get("/api/v1/agents/agt_" + "0" * 32), 404),
        (client.get("/api/v1/nothing-here"), 404),
        (client.post("/api/v1/agents", json={"name": "x", "slug": "x"}), 401),
        (client.post("/api/v1/agents", json={"slug": "Bad Slug"}, headers=auth), 422),
        (client.get("/api/v1/executions?sort=nope"), 400),
        (client.get("/api/v1/executions?status=nope"), 422),
        (post_events(client, auth, execution.id, [ev.step_started(7, new_step_id(), 400)]), 409),
        (post_events(client, auth, execution.id, []), 422),
        (client.get("/api/v1/investigations/exe_" + "0" * 32), 404),
        (client.post("/api/v1/investigations/exe_" + "0" * 32), 404),
        (client.post(f"/api/v1/executions/{execution.id}/replay", json={"mode": "live"}), 422),
        (client.post(f"/api/v1/replays/{replay.id}/claim", headers=auth), 409),
        (client.post(f"/api/v1/replays/{replay.id}/claim"), 401),
        (client.get("/api/v1/replays/rpl_" + "0" * 32), 404),
        (client.delete("/api/v1/health"), 405),
    ]
    for response, status in errors:
        assert response.status_code == status, response.text
        validate(ErrorEnvelope, response.content)


def test_fixture_directory_state() -> None:
    if not FIXTURES:
        pytest.skip("contract/fixtures/ has no fixtures yet: X1 (#2) has not merged")
    covered = {path.name.split(".")[0] for path in FIXTURES}
    missing = FIXTURE_RESOURCES - covered
    assert not missing, f"no fixture for these contract resources: {sorted(missing)}"


@pytest.mark.parametrize("path", FIXTURES, ids=[path.name for path in FIXTURES])
def test_fixture_matches_the_contract(path: Path) -> None:
    adapter = schema_for(path.name)
    assert adapter is not None, (
        f"{path.name} is not mapped to a schema. Name fixtures <resource>.<operation>[.<variant>].json "
        "and map new operations in tests/fixture_map.py."
    )
    try:
        adapter.validate_json(path.read_bytes(), strict=True)
    except ValidationError as exc:
        pytest.fail(f"{path.name} does not match the contract:\n{exc}")
