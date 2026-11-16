"""Contract §10: requesting, claiming and comparing replays."""

import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.errors import ApiError
from app.models import Agent, Execution, Replay, Step
from app.schemas.common import Page
from app.schemas.replays import Replay as ReplaySchema
from app.schemas.replays import ReplayClaim
from app.services import replay as service
from tests import events as ev
from tests.events import new_step_id, post_events
from tests.factories import T0, make_agent, make_execution, make_replay, make_step
from tests.test_conformance import validate

REPLAY_KEYS = {
    "id", "original_execution_id", "replay_execution_id", "mode", "status", "side_effects_authorized", "note",
    "requested_at", "claimed_at", "completed_at", "error", "comparison",
}  # fmt: skip
COMPARISON_KEYS = {
    "original", "replay", "outcome", "duration_delta_ms", "tokens_delta", "step_count_delta", "step_diffs",
}  # fmt: skip
DIFF_KEYS = {
    "ordinal", "name", "original_step_id", "replay_step_id", "change", "original_status", "replay_status",
    "replay_source",
}  # fmt: skip
KEY_ERROR = {"type": "KeyError", "message": "'results'", "stacktrace": None}


@pytest.fixture
def agent(db_session: Session) -> Agent:
    return make_agent(db_session, slug="research-assistant", name="Research Assistant")


@pytest.fixture
def failed(db_session: Session, agent: Agent) -> Execution:
    """The schema-change failure, as stored rows: plan, web_search (data/meta), parse_results (KeyError)."""
    execution = make_execution(
        db_session,
        agent,
        status="failed",
        duration_ms=400,
        step_count=3,
        error=KEY_ERROR,
        input={"question": "q"},
    )
    make_step(db_session, execution, 1, name="plan", type="reasoning", output={"query": "q"})
    make_step(
        db_session, execution, 2, name="web_search", type="tool_call", tool_name="web_search",
        input={"query": "q"}, output={"data": [1], "meta": {}},
    )  # fmt: skip
    make_step(
        db_session, execution, 3, name="parse_results", type="reasoning", status="failed", error=KEY_ERROR
    )
    return execution


def request_replay(client: TestClient, execution_id: str, **body: Any) -> dict[str, Any]:
    response = client.post(f"/api/v1/executions/{execution_id}/replay", json={"mode": "sandbox", **body})
    assert response.status_code == 201, response.text
    validate(ReplaySchema, response.content)
    return response.json()


def claim(client: TestClient, auth: dict, replay_id: str) -> dict[str, Any]:
    response = client.post(f"/api/v1/replays/{replay_id}/claim", headers=auth)
    assert response.status_code == 200, response.text
    validate(ReplayClaim, response.content)
    return response.json()


def start_replay_execution(client: TestClient, auth: dict, original: Execution, replay_id: str) -> str:
    response = client.post(
        "/api/v1/executions",
        json={
            "agent_id": original.agent_id,
            "input": original.input,
            "config": {},
            "replay_of": original.id,
            "replay_id": replay_id,
            "started_at": ev.at(0),  # the event builders time everything from T0
        },
        headers=auth,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def run_replay(client: TestClient, auth: dict, original: Execution, events_for: Any) -> dict[str, Any]:
    """Request, claim and run a replay whose execution sends `events_for()`. Returns the finished replay."""
    replay = request_replay(client, original.id)
    claim(client, auth, replay["id"])
    execution_id = start_replay_execution(client, auth, original, replay["id"])
    assert post_events(client, auth, execution_id, events_for()).status_code == 202
    finished = client.get(f"/api/v1/replays/{replay['id']}")
    validate(ReplaySchema, finished.content)
    assert finished.json()["replay_execution_id"] == execution_id
    return finished.json()


def fixed_run() -> list[dict]:
    """The replay after the parser fix: web_search served from the recording, summarize run live."""
    plan, search, parse, summarize = (new_step_id() for _ in range(4))
    return [
        ev.step_started(1, plan, 0, metadata={"replay_source": "executed"}),
        ev.step_completed(2, plan, 1, output={"query": "q"}),
        ev.step_started(
            3,
            search,
            2,
            name="web_search",
            step_type="tool_call",
            tool_name="web_search",
            metadata={"replay_source": "recorded"},
        ),
        ev.step_completed(4, search, 3, output={"data": [1], "meta": {}}),
        ev.step_started(5, parse, 4, name="parse_results", metadata={"replay_source": "executed"}),
        ev.step_completed(6, parse, 5, output={"sources": 1}),
        ev.step_started(
            7, summarize, 6, name="summarize", step_type="llm_call", metadata={"replay_source": "executed"}
        ),
        ev.step_completed(8, summarize, 300, output={"text": "…"}, tokens_input=40, tokens_output=10),
        ev.execution_completed(9, 310, output={"answer": "…"}),
    ]


def test_request_a_sandbox_replay(db_client: TestClient, failed: Execution) -> None:
    replay = request_replay(db_client, failed.id, note="after the parser fix")
    assert set(replay) == REPLAY_KEYS
    assert replay["id"].startswith("rpl_")
    assert (replay["original_execution_id"], replay["mode"], replay["status"]) == (
        failed.id,
        "sandbox",
        "pending",
    )
    assert (replay["side_effects_authorized"], replay["note"]) == (False, "after the parser fix")
    for key in ("replay_execution_id", "claimed_at", "completed_at", "error", "comparison"):
        assert replay[key] is None, key
    assert db_client.get(f"/api/v1/executions/{failed.id}").json()["replay_ids"] == [replay["id"]]
    assert db_client.get(f"/api/v1/replays/{replay['id']}").json() == replay


def test_a_live_replay_needs_explicit_authorization(
    db_client: TestClient, db_session: Session, failed: Execution
) -> None:
    for body in ({"mode": "live"}, {"mode": "live", "authorize_side_effects": False}):
        refused = db_client.post(f"/api/v1/executions/{failed.id}/replay", json=body)
        assert refused.status_code == 422
        error = refused.json()["error"]
        assert error["code"] == "side_effect_authorization_required"
        assert "authorize_side_effects" in error["message"]
    assert db_session.scalar(select(func.count()).select_from(Replay)) == 0  # nothing was created

    live = request_replay(db_client, failed.id, mode="live", authorize_side_effects=True)
    assert (live["mode"], live["side_effects_authorized"]) == ("live", True)
    # Authorization is meaningless for a sandbox replay and is never recorded for one.
    sandbox = request_replay(db_client, failed.id, mode="sandbox", authorize_side_effects=True)
    assert (sandbox["mode"], sandbox["side_effects_authorized"]) == ("sandbox", False)


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({}, 422, "validation_error"),
        ({"mode": "dry-run"}, 422, "validation_error"),
        ({"mode": "sandbox", "authorize_side_effects": "yes"}, 422, "validation_error"),
        ({"mode": "sandbox", "unknown": 1}, 422, "validation_error"),
    ],
)
def test_replay_request_validation(
    db_client: TestClient, failed: Execution, body: dict, status: int, code: str
) -> None:
    response = db_client.post(f"/api/v1/executions/{failed.id}/replay", json=body)
    assert (response.status_code, response.json()["error"]["code"]) == (status, code)


def test_only_ended_known_executions_can_be_replayed(
    db_client: TestClient, db_session: Session, agent: Agent
) -> None:
    running = make_execution(db_session, agent)
    response = db_client.post(f"/api/v1/executions/{running.id}/replay", json={"mode": "sandbox"})
    assert (response.status_code, response.json()["error"]["code"]) == (409, "conflict")
    unknown = db_client.post("/api/v1/executions/exe_" + "0" * 32 + "/replay", json={"mode": "sandbox"})
    assert unknown.status_code == 404
    assert db_client.get("/api/v1/replays/rpl_" + "0" * 32).status_code == 404
    assert db_client.get("/api/v1/replays/nope").status_code == 404


def test_claim_returns_the_bundle_once(
    db_client: TestClient, db_session: Session, auth: dict, failed: Execution
) -> None:
    replay = request_replay(db_client, failed.id)
    assert db_client.post(f"/api/v1/replays/{replay['id']}/claim").status_code == 401  # workers need the key

    claimed = claim(db_client, auth, replay["id"])
    assert set(claimed) == {"replay", "bundle"}
    assert (claimed["replay"]["status"], claimed["replay"]["id"]) == ("claimed", replay["id"])
    assert claimed["replay"]["claimed_at"] is not None and claimed["replay"]["replay_execution_id"] is None

    bundle = claimed["bundle"]
    assert bundle["original_execution"]["id"] == failed.id
    assert bundle["original_execution"]["input"] == {"question": "q"}
    # Only the tool and LLM calls are recordings; the agent's own steps are re-run, not served.
    assert bundle["recorded_calls"] == [
        {
            "step_name": "web_search",
            "step_type": "tool_call",
            "tool_name": "web_search",
            "occurrence": 1,
            "input": {"query": "q"},
            "output": {"data": [1], "meta": {}},
            "error": None,
        }
    ]

    again = db_client.post(f"/api/v1/replays/{replay['id']}/claim", headers=auth)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "conflict")
    assert "already claimed" in again.json()["error"]["message"]
    assert db_client.post("/api/v1/replays/rpl_" + "0" * 32 + "/claim", headers=auth).status_code == 404


def test_bundle_numbers_repeated_calls_and_keeps_their_errors(
    db_client: TestClient, db_session: Session, auth: dict, agent: Agent
) -> None:
    rate_limited = {"type": "RateLimited", "message": "HTTP 429 Too Many Requests", "stacktrace": None}
    original = make_execution(db_session, agent, status="completed", step_count=6)
    make_step(
        db_session,
        original,
        1,
        name="classify",
        type="llm_call",
        model="demo-llm-1",
        output={"text": "billing"},
    )
    make_step(
        db_session,
        original,
        2,
        name="retrieve_kb",
        type="tool_call",
        tool_name="retrieve_kb",
        status="failed",
        error=rate_limited,
    )
    make_step(
        db_session,
        original,
        3,
        name="retrieve_kb",
        type="tool_call",
        tool_name="retrieve_kb",
        attempt=2,
        status="failed",
        error=rate_limited,
    )
    make_step(
        db_session,
        original,
        4,
        name="retrieve_kb",
        type="tool_call",
        tool_name="retrieve_kb",
        attempt=3,
        output={"articles": []},
    )
    make_step(db_session, original, 5, name="note", type="custom", output="not a call")
    make_step(db_session, original, 6, name="classify", type="llm_call", output={"text": "bug"})

    calls = claim(db_client, auth, request_replay(db_client, original.id)["id"])["bundle"]["recorded_calls"]
    assert [(c["step_type"], c["step_name"], c["tool_name"], c["occurrence"]) for c in calls] == [
        ("llm_call", "classify", None, 1),
        ("tool_call", "retrieve_kb", "retrieve_kb", 1),
        ("tool_call", "retrieve_kb", "retrieve_kb", 2),
        ("tool_call", "retrieve_kb", "retrieve_kb", 3),
        ("llm_call", "classify", None, 2),
    ]
    assert [c["error"] and c["error"]["type"] for c in calls] == [
        None,
        "RateLimited",
        "RateLimited",
        None,
        None,
    ]
    assert calls[3]["output"] == {"articles": []}


def test_a_replay_execution_must_belong_to_a_claimed_replay(
    db_client: TestClient, db_session: Session, auth: dict, failed: Execution, agent: Agent
) -> None:
    replay = request_replay(db_client, failed.id)

    def start(**changes: Any) -> Any:
        body = {
            "agent_id": agent.id,
            "input": {},
            "config": {},
            "replay_of": failed.id,
            "replay_id": replay["id"],
            **changes,
        }
        return db_client.post("/api/v1/executions", json=body, headers=auth)

    assert start().status_code == 409  # not claimed yet
    claim(db_client, auth, replay["id"])
    other = make_execution(db_session, agent, status="failed")
    wrong = start(replay_of=other.id)
    assert (wrong.status_code, wrong.json()["error"]["details"][0]["loc"]) == (422, ["body", "replay_of"])
    assert start(replay_of=None).status_code == 422  # replay_id needs replay_of
    assert start(replay_id="rpl_" + "0" * 32).status_code == 404

    started = start()
    assert started.status_code == 201
    assert (
        db_client.get(f"/api/v1/replays/{replay['id']}").json()["replay_execution_id"] == started.json()["id"]
    )
    assert start().status_code == 409  # a replay runs once
    assert (
        db_session.scalar(
            select(func.count()).select_from(Execution).where(Execution.replay_id == replay["id"])
        )
        == 1
    )


def test_a_fixed_replay_is_compared_step_by_step(
    db_client: TestClient, db_session: Session, auth: dict, failed: Execution
) -> None:
    replay = run_replay(db_client, auth, failed, fixed_run)
    assert (replay["status"], replay["error"]) == ("completed", None)
    assert replay["completed_at"] is not None

    comparison = replay["comparison"]
    assert set(comparison) == COMPARISON_KEYS and all(set(d) == DIFF_KEYS for d in comparison["step_diffs"])
    assert comparison["outcome"] == "fixed"
    assert (comparison["original"]["id"], comparison["original"]["status"]) == (failed.id, "failed")
    assert (comparison["replay"]["id"], comparison["replay"]["status"]) == (
        replay["replay_execution_id"],
        "completed",
    )
    assert comparison["replay"]["replay_of"] == failed.id
    assert (comparison["duration_delta_ms"], comparison["step_count_delta"]) == (310 - 400, 1)
    assert (
        comparison["tokens_delta"] is None
    )  # the original reported no tokens, so there is nothing to subtract

    diffs = comparison["step_diffs"]
    assert [
        (d["ordinal"], d["name"], d["change"], d["original_status"], d["replay_status"], d["replay_source"])
        for d in diffs
    ] == [
        (1, "plan", "unchanged", "completed", "completed", "executed"),
        (2, "web_search", "unchanged", "completed", "completed", "recorded"),  # served from the recording
        (3, "parse_results", "status_changed", "failed", "completed", "executed"),  # the fix
        (4, "summarize", "added", None, "completed", "executed"),  # ran live: the original never got here
    ]
    assert diffs[3]["original_step_id"] is None and diffs[3]["replay_step_id"].startswith("stp_")
    assert diffs[2]["original_step_id"] != diffs[2]["replay_step_id"]

    # The replay is an execution like any other, linked both ways.
    original = db_client.get(f"/api/v1/executions/{failed.id}").json()
    assert original["replay_ids"] == [replay["id"]]
    listed = db_client.get(f"/api/v1/executions?replay_of={failed.id}").json()["items"]
    assert [item["id"] for item in listed] == [replay["replay_execution_id"]]


def execution_with(
    session: Session,
    agent: Agent,
    status: str,
    steps: list[tuple[str, str, dict | None]],
    error: dict | None = None,
) -> tuple[Execution, list[Step]]:
    execution = Execution(
        id=f"exe_{'0' * 31}{len(steps)}", agent_id=agent.id, status=status, error=error, config={}
    )
    rows = [
        Step(
            id=f"stp_{index:032x}",
            ordinal=index,
            name=name,
            status=step_status,
            error=step_error,
            metadata_={},
        )
        for index, (name, step_status, step_error) in enumerate(steps, 1)
    ]
    return execution, rows


TYPE_ERROR = {"type": "TypeError", "message": "NoneType", "stacktrace": None}
FAILED_AT_PARSE = [("web_search", "completed", None), ("parse_results", "failed", KEY_ERROR)]


@pytest.mark.parametrize(
    ("original", "replay", "expected"),
    [
        (("failed", FAILED_AT_PARSE, KEY_ERROR), ("completed", [("web_search", "completed", None)], None), "fixed"),
        (("completed", [("a", "completed", None)], None), ("failed", FAILED_AT_PARSE, KEY_ERROR), "regressed"),
        (("completed", [("a", "completed", None)], None), ("completed", [("b", "completed", None)], None), "both_succeeded"),
        (("failed", FAILED_AT_PARSE, KEY_ERROR), ("failed", FAILED_AT_PARSE, {**KEY_ERROR, "message": "'items'"}), "same_failure"),
        # same step, different error type
        (("failed", FAILED_AT_PARSE, KEY_ERROR), ("failed", [("web_search", "completed", None), ("parse_results", "failed", TYPE_ERROR)], TYPE_ERROR), "different_failure"),
        # same error type, different step
        (("failed", FAILED_AT_PARSE, KEY_ERROR), ("failed", [("web_search", "completed", None), ("summarize", "failed", KEY_ERROR)], KEY_ERROR), "different_failure"),
        # failures outside any step are compared by error type alone
        (("failed", [], KEY_ERROR), ("failed", [], KEY_ERROR), "same_failure"),
        (("failed", [], KEY_ERROR), ("failed", [], TYPE_ERROR), "different_failure"),
        (("timed_out", [("a", "running", None)], None), ("completed", [("a", "completed", None)], None), "inconclusive"),
        (("failed", FAILED_AT_PARSE, KEY_ERROR), ("timed_out", [("web_search", "running", None)], None), "inconclusive"),
        (("timed_out", [], None), ("timed_out", [], None), "inconclusive"),
    ],
    ids=[
        "fixed", "regressed", "both_succeeded", "same_failure", "different-error-type", "different-step",
        "no-step-same-error", "no-step-different-error", "original-timed-out", "replay-timed-out", "both-timed-out",
    ],
)  # fmt: skip
def test_outcome_rule(original: tuple, replay: tuple, expected: str) -> None:
    agent = Agent(id="agt_" + "a" * 32)
    original_execution, original_steps = execution_with(None, agent, original[0], original[1], original[2])
    replay_execution, replay_steps = execution_with(None, agent, replay[0], replay[1], replay[2])
    assert (
        service.determine_outcome(original_execution, original_steps, replay_execution, replay_steps)
        == expected
    )


def test_step_diff_alignment() -> None:
    def step(
        ordinal: int, name: str, status: str = "completed", output: Any = None, source: str | None = None
    ) -> Step:
        metadata = {"replay_source": source} if source else {}
        return Step(
            id=f"stp_{ordinal:031x}{'a' if source else 'b'}",
            ordinal=ordinal,
            name=name,
            status=status,
            output=output,
            metadata_=metadata,
        )

    original = [
        step(1, "plan", output=1),
        step(2, "search", output={"n": 1}),
        step(3, "parse", "failed"),
        step(4, "old_step"),
    ]
    replay = [
        step(1, "plan", output=1, source="executed"),
        step(2, "search", output={"n": 2}, source="recorded"),
        step(3, "validate", source="executed"),  # a different step now sits at ordinal 3
        step(5, "submit", "failed", source="blocked"),
        step(6, "odd", source="not-a-source"),
    ]
    rows = [
        (d["ordinal"], d["name"], d["change"], d["original_status"], d["replay_status"], d["replay_source"])
        for d in service.diff_steps(original, replay)
    ]
    assert rows == [
        (1, "plan", "unchanged", "completed", "completed", "executed"),
        (2, "search", "output_changed", "completed", "completed", "recorded"),
        (3, "parse", "removed", "failed", None, None),
        (3, "validate", "added", None, "completed", "executed"),
        (4, "old_step", "removed", "completed", None, None),
        (5, "submit", "added", None, "failed", "blocked"),
        (6, "odd", "added", None, "completed", None),  # an unknown value is not passed on
    ]
    assert service.diff_steps([], []) == []


def test_other_outcomes_through_the_api(
    db_client: TestClient, db_session: Session, auth: dict, failed: Execution
) -> None:
    def same_failure() -> list[dict]:
        search, parse = new_step_id(), new_step_id()
        return [
            ev.step_started(1, new_step_id(), 0),
            ev.step_started(2, search, 2, name="web_search", step_type="tool_call", tool_name="web_search"),
            ev.step_completed(3, search, 3, output={"data": [1], "meta": {}}),
            ev.step_started(4, parse, 4, name="parse_results"),
            ev.step_failed(5, parse, 5),
            ev.execution_failed(6, 6),
        ]

    assert run_replay(db_client, auth, failed, same_failure)["comparison"]["outcome"] == "same_failure"

    def different_failure() -> list[dict]:
        step = new_step_id()
        return [
            ev.step_started(1, step, 0, name="summarize"),
            ev.step_failed(2, step, 1, error=TYPE_ERROR),
            ev.execution_failed(3, 2, error=TYPE_ERROR),
        ]

    assert (
        run_replay(db_client, auth, failed, different_failure)["comparison"]["outcome"] == "different_failure"
    )
    assert (
        run_replay(db_client, auth, failed, lambda: [ev.execution_timed_out(1, 5)])["comparison"]["outcome"]
        == "inconclusive"
    )

    replays = db_client.get(f"/api/v1/replays?original_execution_id={failed.id}").json()
    assert replays["total"] == 3 and {item["status"] for item in replays["items"]} == {"completed"}
    # Replays never become part of the agent's baseline or recent history, but each is an execution.
    assert db_client.get("/api/v1/executions?is_replay=true").json()["total"] == 3


def test_a_replay_execution_that_never_ends_leaves_the_replay_claimed(
    db_client: TestClient, db_session: Session, auth: dict, failed: Execution
) -> None:
    replay = request_replay(db_client, failed.id)
    claim(db_client, auth, replay["id"])
    execution_id = start_replay_execution(db_client, auth, failed, replay["id"])
    post_events(db_client, auth, execution_id, [ev.step_started(1, new_step_id(), 0)])
    current = db_client.get(f"/api/v1/replays/{replay['id']}").json()
    assert (current["status"], current["comparison"], current["replay_execution_id"]) == (
        "claimed",
        None,
        execution_id,
    )


def test_list_replays(
    db_client: TestClient, db_session: Session, auth: dict, failed: Execution, agent: Agent
) -> None:
    other = make_execution(db_session, agent, status="completed")
    a = make_replay(db_session, failed, requested_at=T0)
    b = make_replay(
        db_session,
        other,
        status="claimed",
        requested_at=T0.replace(minute=1),
        claimed_at=T0.replace(minute=2),
    )
    c = make_replay(
        db_session, failed, mode="live", side_effects_authorized=True, requested_at=T0.replace(minute=3)
    )
    names = {a.id: "a", b.id: "b", c.id: "c"}

    def listed(query: str = "") -> str:
        response = db_client.get(f"/api/v1/replays{query}")
        assert response.status_code == 200, response.text
        validate(Page[ReplaySchema], response.content)
        return "".join(names[item["id"]] for item in response.json()["items"])

    assert listed() == "cba"  # newest request first
    assert listed("?sort=requested_at") == "abc"
    assert listed("?status=pending") == "ca"  # what a worker polls
    assert listed("?status=claimed,completed") == "b"
    assert listed(f"?original_execution_id={failed.id}") == "ca"
    assert listed(f"?original_execution_id={failed.id}&status=claimed") == ""
    assert listed("?limit=1&offset=1") == "b"
    assert (
        db_client.get("/api/v1/replays?status=pending", headers=auth).status_code == 200
    )  # with or without the key
    assert db_client.get("/api/v1/replays?status=done").status_code == 422
    assert db_client.get("/api/v1/replays?sort=mode").status_code == 400
    assert db_client.get("/api/v1/replays?limit=1").json()["total"] == 3


def test_two_workers_racing_for_one_replay(migrated_database: None) -> None:
    engine = get_engine()
    with Session(engine, expire_on_commit=False) as setup:
        agent = make_agent(setup)
        original = make_execution(setup, agent, status="failed")
        replay = make_replay(setup, original)
        setup.commit()

    results: list[Any] = []
    barrier = threading.Barrier(4)

    def worker() -> None:
        with Session(engine, expire_on_commit=False) as session:
            barrier.wait()
            try:
                results.append(service.claim_replay(session, replay.id).replay.status)
            except ApiError as exc:
                results.append(exc.code)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert sorted(results) == ["claimed", "conflict", "conflict", "conflict"]
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(Replay).where(Replay.id == replay.id))
            cleanup.execute(delete(Execution).where(Execution.id == original.id))
            cleanup.execute(delete(Agent).where(Agent.id == agent.id))
            cleanup.commit()
