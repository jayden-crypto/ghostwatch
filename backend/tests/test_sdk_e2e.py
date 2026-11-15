"""The SDK against the real API over HTTP: what an instrumented agent does becomes a correct trace."""

import time

import ghostwatch as gw
import httpx2
import pytest

from app.config import get_settings
from app.schemas.agents import Agent
from app.schemas.common import Page
from app.schemas.traces import Trace
from tests.test_conformance import validate


@gw.tool(side_effects=False)
def web_search(query: str) -> dict:
    if query == "rate-limited":
        raise RuntimeError("HTTP 429")
    return {"data": [query], "meta": {"total": 1}}


@gw.tool(side_effects=True)
def submit_invoice(invoice: dict) -> dict:
    return {"submitted": invoice["id"]}


def init_sdk(api_url: str) -> None:
    gw.init(
        agent=gw.Agent(slug="research-assistant", name="Research Assistant", framework="custom"),
        api_url=api_url,
        api_key=get_settings().ghostwatch_api_key,
        flush_interval=0.05,
        batch_size=3,
    )


def test_an_instrumented_run_becomes_a_correct_trace(live_api: str) -> None:
    init_sdk(live_api)
    with gw.execution(
        input={"question": "q"}, config={"model": "fake-llm", "expected_steps": ["web_search"]}, tags=["e2e"]
    ) as run:
        with run.step("plan", type="reasoning", input={"question": "q"}) as plan:
            plan.output = {"queries": ["rate-limited", "q"]}
        with run.step("research") as research:
            try:
                web_search("rate-limited")
            except RuntimeError:
                run.log("retrying", level="warning")
            results = web_search("q")
            with run.step("summarize", type="llm_call", model="fake-llm") as summarize:
                summarize.output = "summary"
                summarize.tokens_input, summarize.tokens_output = 800, 90
            research.output = {"count": len(results["data"])}
        submit_invoice({"id": 17})
        run.output = {"answer": "summary"}
    assert gw.flush() is True
    assert run.id is not None

    with httpx2.Client(base_url=live_api) as http:
        trace = validate(Trace, http.get(f"/executions/{run.id}/trace").content)
        agents = validate(Page[Agent], http.get("/agents").content)

    execution = trace.execution
    assert (execution.status, execution.step_count, execution.agent_name) == (
        "completed",
        6,
        "Research Assistant",
    )
    assert (execution.input, execution.output, execution.tags) == (
        {"question": "q"},
        {"answer": "summary"},
        ["e2e"],
    )
    assert execution.config.model == "fake-llm" and execution.config.expected_steps == ["web_search"]
    assert (execution.tokens_input, execution.tokens_output, execution.tokens_total) == (800, 90, 890)
    assert execution.duration_ms is not None and execution.error is None
    assert trace.event_count == 14  # 6 steps started and ended, one log, one terminal event

    steps = trace.steps
    assert [step.name for step in steps] == [
        "plan",
        "research",
        "web_search",
        "web_search",
        "summarize",
        "submit_invoice",
    ]
    assert [step.depth for step in steps] == [0, 0, 1, 1, 1, 0]
    assert [step.type for step in steps] == [
        "reasoning",
        "custom",
        "tool_call",
        "tool_call",
        "llm_call",
        "tool_call",
    ]
    assert [step.status for step in steps] == [
        "completed",
        "completed",
        "failed",
        "completed",
        "completed",
        "completed",
    ]
    assert [step.attempt for step in steps] == [1, 1, 1, 2, 1, 1]
    assert [step.ordinal for step in steps] == [1, 2, 3, 4, 5, 6]
    research, failed_search, retried_search, summarize, submit = steps[1:]
    assert (
        failed_search.parent_step_id
        == retried_search.parent_step_id
        == summarize.parent_step_id
        == research.id
    )
    assert (failed_search.error.type, failed_search.error.message) == ("RuntimeError", "HTTP 429")
    assert "Traceback" in failed_search.error.stacktrace
    assert (retried_search.input, retried_search.output) == (
        {"query": "q"},
        {"data": ["q"], "meta": {"total": 1}},
    )
    assert retried_search.tool_name == "web_search" and retried_search.metadata == {"side_effects": False}
    assert (summarize.model, summarize.tokens_input, summarize.tokens_output) == ("fake-llm", 800, 90)
    assert submit.metadata == {"side_effects": True} and submit.output == {"submitted": 17}
    assert research.output == {"count": 1}
    assert all(step.offset_ms >= 0 and step.duration_ms >= 0 for step in steps)
    assert [step.offset_ms for step in steps] == sorted(step.offset_ms for step in steps)

    assert [(agent.slug, agent.stats.total_executions, agent.stats.health) for agent in agents.items] == [
        ("research-assistant", 1, "healthy")
    ]


def test_an_agent_exception_fails_the_execution_and_still_propagates(live_api: str) -> None:
    init_sdk(live_api)
    with pytest.raises(KeyError), gw.execution(input={"question": "q"}) as run:
        payload = web_search("q")
        with run.step("parse_results", type="reasoning"):
            payload["results"]
    assert gw.flush() is True

    with httpx2.Client(base_url=live_api) as http:
        trace = validate(Trace, http.get(f"/executions/{run.id}/trace").content)
    assert trace.execution.status == "failed"
    assert (trace.execution.error.type, trace.execution.error.message) == ("KeyError", "'results'")
    assert [(step.name, step.status) for step in trace.steps] == [
        ("web_search", "completed"),
        ("parse_results", "failed"),
    ]
    assert trace.steps[1].error.type == "KeyError"
    assert trace.steps[0].output == {
        "data": ["q"],
        "meta": {"total": 1},
    }  # the evidence the investigation will use


def test_two_runs_of_one_agent_are_separate_executions(live_api: str) -> None:
    init_sdk(live_api)
    runs = []
    for question in ("a", "b"):
        with gw.execution(input={"question": question}) as run:
            web_search(question)
        runs.append(run)
    assert gw.flush() is True
    with httpx2.Client(base_url=live_api) as http:
        page = http.get("/executions").json()
    # Both runs can start within the same millisecond, so their order is not asserted.
    assert sorted(item["id"] for item in page["items"]) == sorted(run.id for run in runs)
    assert {item["agent_id"] for item in page["items"]} == {page["items"][0]["agent_id"]}
    assert [item["step_count"] for item in page["items"]] == [1, 1]


def test_the_running_app_times_out_an_execution_that_goes_quiet(live_api: str) -> None:
    """The sweeper is started by the app's lifespan: no events for timeout_ms, and the run is timed out."""
    headers = {"Authorization": f"Bearer {get_settings().ghostwatch_api_key}"}
    with httpx2.Client(base_url=live_api, headers=headers) as http:
        agent = http.post("/agents", json={"slug": "support-triage", "name": "Support Triage"}).json()
        created = http.post(
            "/executions", json={"agent_id": agent["id"], "input": {}, "config": {"timeout_ms": 300}}
        )
        execution_id = created.json()["id"]
        assert created.json()["status"] == "running"

        deadline = time.monotonic() + 10
        status = "running"
        while status == "running" and time.monotonic() < deadline:
            time.sleep(0.05)
            status = http.get(f"/executions/{execution_id}").json()["status"]
        assert status == "timed_out"

        trace = validate(Trace, http.get(f"/executions/{execution_id}/trace").content)
    assert [(anomaly.type, anomaly.severity) for anomaly in trace.anomalies] == [("stale_execution", "high")]
    assert trace.execution.error.type == "TimeoutError"
    assert trace.event_count == 1
