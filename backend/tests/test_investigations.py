"""Contract §9 end to end: auto-triggered and manual investigations through the API, on Postgres."""

import contextlib
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Execution, Investigation
from app.providers.llm.base import Proposal, ProviderError, ProviderResult
from app.schemas.common import Page
from app.schemas.investigations import Investigation as InvestigationSchema
from app.services import ingest
from app.services.investigation import engine
from tests import events as ev
from tests.events import new_step_id, post_events
from tests.factories import T0, make_agent, make_execution, make_investigation
from tests.test_conformance import validate

INVESTIGATION_KEYS = {
    "id", "execution_id", "status", "trigger", "provider", "model", "created_at", "completed_at", "error", "report",
}  # fmt: skip
REPORT_KEYS = {
    "summary", "failing_step_id", "root_cause", "facts", "hypotheses", "recommendations", "evidence_gaps",
    "relevant_step_ids",
}  # fmt: skip


@pytest.fixture
def execution(db_session: Session) -> Execution:
    agent = make_agent(db_session, slug="research-assistant", name="Research Assistant")
    return make_execution(db_session, agent, config={"expected_steps": ["web_search", "parse_results"]})


def schema_change_events() -> tuple[list[dict], str, str]:
    search, parse = new_step_id(), new_step_id()
    events = [
        ev.step_started(
            1,
            search,
            10,
            name="web_search",
            step_type="tool_call",
            tool_name="web_search",
            input={"query": "q"},
        ),
        ev.step_completed(2, search, 400, output={"data": [{"title": "t"}], "meta": {"total": 1}}),
        ev.step_started(3, parse, 410, name="parse_results"),
        ev.step_failed(4, parse, 420),
        ev.execution_failed(5, 430),
    ]
    return events, search, parse


def healthy_events() -> list[dict]:
    search, parse = new_step_id(), new_step_id()
    return [
        ev.step_started(1, search, 10, name="web_search", step_type="tool_call", tool_name="web_search"),
        ev.step_completed(2, search, 400, output={"results": []}),
        ev.step_started(3, parse, 410, name="parse_results"),
        ev.step_completed(4, parse, 420),
        ev.execution_completed(5, 430),
    ]


def latest(client: TestClient, execution_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/investigations/{execution_id}")
    assert response.status_code == 200, response.text
    validate(InvestigationSchema, response.content)
    return response.json()


def count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Investigation))


def test_a_failed_execution_is_investigated_automatically_and_confirmed(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    events, search, parse = schema_change_events()
    assert post_events(db_client, auth, execution.id, events).json()["execution_status"] == "failed"

    investigation = latest(db_client, execution.id)
    assert set(investigation) == INVESTIGATION_KEYS and set(investigation["report"]) == REPORT_KEYS
    assert (investigation["status"], investigation["trigger"]) == ("completed", "auto_failure")
    assert (investigation["provider"], investigation["model"], investigation["error"]) == (
        "rule_based",
        None,
        None,
    )
    assert investigation["execution_id"] == execution.id and investigation["completed_at"] is not None

    report = investigation["report"]
    assert report["root_cause"] == {
        "status": "confirmed",
        "statement": (
            "Step 2 parse_results read the key 'results', which the output of Step 1 web_search (tool web_search) "
            "does not contain. That output's keys are: data, meta."
        ),
        "hypothesis_id": "H1",
        "signature": "missing_key_in_upstream_output",
    }
    assert report["failing_step_id"] == parse
    assert report["relevant_step_ids"] == [search, parse]

    # Every claim leads to the exact stored step that proves it.
    facts = {fact["id"]: fact for fact in report["facts"]}
    supporting = report["hypotheses"][0]["supporting_fact_ids"]
    cited = [facts[fact_id] for fact_id in supporting]
    assert [fact["statement"] for fact in cited] == [
        "Step 2 parse_results failed with KeyError: 'results'.",
        "Step 1 web_search (tool_call, completed) returned an object with keys: data, meta.",
    ]
    assert [fact["evidence"][0]["ref_id"] for fact in cited] == [parse, search]
    assert cited[1]["evidence"][0]["excerpt"] == '{"data":[{"title":"t"}],"meta":{"total":1}}'
    trace_steps = {s["id"] for s in db_client.get(f"/api/v1/executions/{execution.id}/trace").json()["steps"]}
    step_refs = {
        item["ref_id"] for fact in report["facts"] for item in fact["evidence"] if item["kind"] == "step"
    }
    assert step_refs <= trace_steps and step_refs

    detail = db_client.get(f"/api/v1/executions/{execution.id}").json()
    assert detail["has_investigation"] is True
    assert "llm_raw_response" not in db_client.get(f"/api/v1/investigations/{execution.id}").text


def test_a_ghost_completion_is_investigated_automatically(
    db_client: TestClient, db_session: Session, auth: dict
) -> None:
    agent = make_agent(db_session, slug="invoice-processor")
    run = make_execution(db_session, agent, config={"expected_steps": ["validate", "submit_invoice"]})
    step = new_step_id()
    post_events(
        db_client, auth, run.id,
        [ev.step_started(1, step, 10, name="validate"), ev.step_completed(2, step, 200), ev.execution_completed(3, 250)],
    )  # fmt: skip
    investigation = latest(db_client, run.id)
    assert (investigation["status"], investigation["trigger"]) == ("completed", "auto_anomaly")
    root_cause = investigation["report"]["root_cause"]
    assert (root_cause["status"], root_cause["signature"]) == ("confirmed", "ghost_completion")
    assert "submit_invoice never completed" in root_cause["statement"]
    assert investigation["report"]["failing_step_id"] is None
    assert investigation["report"]["summary"].startswith(
        "The execution completed. Anomalies raised on it: ghost_completion."
    )


def test_healthy_and_mildly_anomalous_runs_are_not_investigated(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    post_events(db_client, auth, execution.id, healthy_events())
    missing = db_client.get(f"/api/v1/investigations/{execution.id}")
    assert missing.status_code == 404
    assert missing.json()["error"] == {
        "code": "not_found",
        "message": f"Execution {execution.id} has not been investigated.",
        "details": None,
    }

    retried = make_execution(
        db_session, db_session.get(Execution, execution.id).agent_id and make_agent(db_session)
    )
    events, seq = [], 0
    for attempt in (1, 2, 3):
        step = new_step_id()
        events.append(
            ev.step_started(
                seq + 1,
                step,
                attempt * 10,
                name="retrieve_kb",
                step_type="tool_call",
                tool_name="retrieve_kb",
                attempt=attempt,
            )
        )
        events.append(ev.step_completed(seq + 2, step, attempt * 10 + 5))
        seq += 2
    events.append(ev.execution_completed(seq + 1, 100))
    post_events(db_client, auth, retried.id, events)
    assert (
        db_client.get(f"/api/v1/anomalies?execution_id={retried.id}").json()["items"][0]["severity"]
        == "medium"
    )
    assert db_client.get(f"/api/v1/investigations/{retried.id}").status_code == 404
    assert count(db_session) == 0


def test_an_execution_the_sweeper_times_out_is_investigated(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    step = new_step_id()
    post_events(
        db_client,
        auth,
        execution.id,
        [ev.step_started(1, step, 10, name="web_search", step_type="tool_call", tool_name="web_search")],
    )
    now = T0 + timedelta(minutes=10)
    execution.last_event_at = now - timedelta(minutes=6)
    db_session.flush()
    assert ingest.time_out_if_stale(db_session, execution.id, now) is True

    queued = db_client.get(f"/api/v1/investigations/{execution.id}").json()
    assert (queued["status"], queued["trigger"], queued["report"], queued["completed_at"]) == (
        "queued",
        "auto_failure",
        None,
        None,
    )
    validate(InvestigationSchema, db_client.get(f"/api/v1/investigations/{execution.id}").content)

    # The sweeper runs queued investigations at the end of each pass.
    assert engine.run_queued(lambda: contextlib.nullcontext(db_session)) == 1
    done = latest(db_client, execution.id)
    assert (done["status"], done["report"]["root_cause"]["signature"]) == ("completed", "timeout_in_step")
    assert done["report"]["failing_step_id"] == step
    assert done["report"]["root_cause"]["statement"] == (
        "The execution timed out while Step 1 web_search was running; that step never finished."
    )
    assert engine.run_queued(lambda: contextlib.nullcontext(db_session)) == 0


def test_manual_investigation_lifecycle(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    running = db_client.post(f"/api/v1/investigations/{execution.id}")
    assert running.status_code == 409
    assert running.json()["error"]["code"] == "conflict"

    post_events(db_client, auth, execution.id, healthy_events())
    first = db_client.post(f"/api/v1/investigations/{execution.id}")  # no body at all
    assert first.status_code == 202
    validate(InvestigationSchema, first.content)
    assert (first.json()["status"], first.json()["trigger"], first.json()["report"]) == (
        "queued",
        "manual",
        None,
    )

    done = latest(db_client, execution.id)  # the background task has run
    assert (done["id"], done["status"]) == (first.json()["id"], "completed")
    assert (
        done["report"]["root_cause"]["status"] == "insufficient_evidence"
    )  # nothing went wrong, and it says so
    assert done["report"]["hypotheses"] == []

    again = db_client.post(f"/api/v1/investigations/{execution.id}", json={})
    assert again.status_code == 200
    assert again.json() == done
    assert db_client.post(f"/api/v1/investigations/{execution.id}", json={"force": False}).status_code == 200

    forced = db_client.post(f"/api/v1/investigations/{execution.id}", json={"force": True})
    assert forced.status_code == 202 and forced.json()["id"] != done["id"]
    assert latest(db_client, execution.id)["id"] == forced.json()["id"]
    assert count(db_session) == 2

    assert db_client.post("/api/v1/investigations/exe_" + "0" * 32).status_code == 404
    assert (
        db_client.get("/api/v1/investigations/exe_" + "0" * 32)
        .json()["error"]["message"]
        .endswith("does not exist.")
    )
    assert (
        db_client.post(
            f"/api/v1/investigations/{execution.id}", json={"force": "yes please", "x": 1}
        ).status_code
        == 422
    )


def test_an_investigation_already_in_flight_is_returned_not_duplicated(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    post_events(db_client, auth, execution.id, healthy_events())
    in_flight = make_investigation(
        db_session, execution, status="running", created_at=T0 + timedelta(hours=1)
    )
    for body in ({}, {"force": True}):
        response = db_client.post(f"/api/v1/investigations/{execution.id}", json=body)
        assert (response.status_code, response.json()["id"], response.json()["status"]) == (
            202,
            in_flight.id,
            "running",
        )
    assert count(db_session) == 1


def test_running_an_investigation_twice_does_nothing_the_second_time(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    events, _, _ = schema_change_events()
    post_events(db_client, auth, execution.id, events)
    investigation = db_session.scalars(select(Investigation)).one()
    completed_at, report = investigation.completed_at, investigation.report
    engine.run(investigation.id, lambda: contextlib.nullcontext(db_session))
    assert (investigation.status, investigation.completed_at, investigation.report) == (
        "completed",
        completed_at,
        report,
    )


def test_a_crash_inside_the_pipeline_is_recorded_as_a_failed_investigation(
    db_client: TestClient,
    db_session: Session,
    auth: dict,
    execution: Execution,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(engine, "build_report", explode)
    events, _, _ = schema_change_events()
    assert post_events(db_client, auth, execution.id, events).status_code == 202  # ingestion is unaffected

    failed = latest(db_client, execution.id)
    assert (failed["status"], failed["report"]) == ("failed", None)
    assert failed["error"] == {
        "type": "RuntimeError",
        "message": "The investigation could not be completed; see the backend log.",
        "stacktrace": None,
    }
    assert "secret internal detail" not in str(failed)
    assert db_session.get(Execution, execution.id).status == "failed"  # the execution itself is intact

    monkeypatch.undo()
    retry = db_client.post(
        f"/api/v1/investigations/{execution.id}"
    )  # a failed one does not block a new attempt
    assert retry.status_code == 202 and retry.json()["id"] != failed["id"]
    assert latest(db_client, execution.id)["status"] == "completed"


class StubFable:
    name = "fable"

    def __init__(self, proposal: dict | None = None, error: str | None = None) -> None:
        self.proposal, self.error = proposal, error

    def investigate(self, facts: list, digest: dict, confirmed: list) -> ProviderResult:
        if self.error:
            raise ProviderError(self.error)
        return ProviderResult(
            proposal=Proposal.model_validate(self.proposal),
            model="claude-fable-5-2",
            raw={"id": "msg_secret", "usage": {}},
        )


def test_llm_hypotheses_are_verified_stored_and_labelled_with_the_model(
    db_client: TestClient,
    db_session: Session,
    auth: dict,
    execution: Execution,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = {
        "hypotheses": [
            {"statement": "The search API moved to a v2 response format.", "confidence": "medium", "reasoning": "F4.",
             "supporting_fact_ids": ["F4"], "contradicting_fact_ids": [], "relevant_step_ids": []},
            {"statement": "Invented.", "confidence": "high", "reasoning": "?", "supporting_fact_ids": ["F77"],
             "contradicting_fact_ids": [], "relevant_step_ids": ["stp_" + "9" * 32]},
        ],
        "recommendations": [{"action": "Add a contract test.", "rationale": "Catches drift.", "hypothesis_index": 0}],
        "root_cause": {"hypothesis_index": 1, "status": "confirmed"},
        "evidence_gaps": [],
    }  # fmt: skip
    monkeypatch.setattr(engine, "make_provider", lambda settings: (StubFable(proposal), None))
    events, _, _ = schema_change_events()
    post_events(db_client, auth, execution.id, events)

    investigation = latest(db_client, execution.id)
    assert (investigation["provider"], investigation["model"]) == ("fable", "claude-fable-5-2")
    report = investigation["report"]
    assert (report["root_cause"]["status"], report["root_cause"]["signature"]) == (
        "confirmed",
        "missing_key_in_upstream_output",
    )
    assert [h["statement"] for h in report["hypotheses"]][1:] == [
        "The search API moved to a v2 response format."
    ]
    assert any("cited fact id(s) that do not exist (F77)" in gap for gap in report["evidence_gaps"])
    assert any("labelled its root cause as confirmed" in gap for gap in report["evidence_gaps"])

    row = db_session.scalars(select(Investigation)).one()
    assert row.llm_raw_response == {"id": "msg_secret", "usage": {}}  # kept for audit
    assert "msg_secret" not in db_client.get(f"/api/v1/investigations/{execution.id}").text  # never served
    assert "msg_secret" not in db_client.get("/api/v1/investigations").text


def test_when_the_llm_fails_the_report_is_rule_based_and_says_so(
    db_client: TestClient,
    db_session: Session,
    auth: dict,
    execution: Execution,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        engine, "make_provider", lambda settings: (StubFable(error="timed out after 60 s"), None)
    )
    events, _, _ = schema_change_events()
    post_events(db_client, auth, execution.id, events)
    investigation = latest(db_client, execution.id)
    assert (investigation["status"], investigation["provider"], investigation["model"]) == (
        "completed",
        "rule_based",
        None,
    )
    assert investigation["report"]["root_cause"]["status"] == "confirmed"
    assert investigation["report"]["evidence_gaps"][-1] == (
        "No LLM hypotheses: the fable provider timed out after 60 s. This report contains deterministic findings only."
    )


def test_list_investigations(
    db_client: TestClient, db_session: Session, auth: dict, execution: Execution
) -> None:
    other_agent = make_agent(db_session, slug="invoice-processor")
    other = make_execution(db_session, other_agent, status="failed")
    events, _, _ = schema_change_events()
    post_events(db_client, auth, execution.id, events)  # completed, auto
    queued = make_investigation(db_session, other, status="queued", created_at=T0)
    failed = make_investigation(
        db_session, other, status="failed", created_at=T0 + timedelta(minutes=1), completed_at=T0 + timedelta(minutes=2),
        error={"type": "RuntimeError", "message": "x", "stacktrace": None},
    )  # fmt: skip
    completed_id = latest(db_client, execution.id)["id"]

    def listed(query: str = "") -> list[str]:
        response = db_client.get(f"/api/v1/investigations{query}")
        assert response.status_code == 200, response.text
        validate(Page[InvestigationSchema], response.content)
        return [item["id"] for item in response.json()["items"]]

    page = db_client.get("/api/v1/investigations").json()
    assert (page["total"], page["limit"], page["offset"]) == (3, 50, 0)
    assert listed() == [completed_id, failed.id, queued.id]  # newest first
    assert listed("?sort=created_at") == [queued.id, failed.id, completed_id]
    assert listed("?status=completed") == [completed_id]
    assert listed("?status=queued,failed") == [failed.id, queued.id]
    assert listed(f"?agent_id={other_agent.id}") == [failed.id, queued.id]
    assert listed(f"?agent_id={other_agent.id}&status=completed") == []
    assert listed("?limit=1&offset=1") == [failed.id]
    assert page["items"][0]["report"]["root_cause"]["status"] == "confirmed"  # the list carries the reports
    assert db_client.get("/api/v1/investigations?status=done").status_code == 422
    assert db_client.get("/api/v1/investigations?sort=status").status_code == 400
