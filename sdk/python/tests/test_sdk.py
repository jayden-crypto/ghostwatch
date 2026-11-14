from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from conftest import AGENT, API_KEY, StubApi, closed_port_url, wait_for

import ghostwatch as gw
from ghostwatch.execution import to_json

STEP_ID = re.compile(r"stp_[0-9a-f]{32}")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")


@gw.tool
def web_search(query: str, limit: int = 3) -> dict:
    return {"results": [f"{query}-{index}" for index in range(limit)]}


@gw.tool(side_effects=True, name="submit_invoice")
def submit(invoice: dict) -> dict:
    return {"submitted": invoice["id"]}


def types(events: list[dict]) -> list[str]:
    return [event["type"] for event in events]


def test_a_nested_run_becomes_the_contract_event_stream(sdk: StubApi) -> None:
    with gw.execution(
        input={"question": "q"}, config={"model": "m", "expected_steps": ["web_search"]}, tags=["t"]
    ) as run:
        with run.step("plan", type="reasoning", input={"q": "q"}) as plan:
            plan.output = {"queries": ["q"]}
        with run.step("research", metadata={"phase": 1}) as research:
            results = web_search("q", limit=2)
            run.log("searched")
            with run.step("summarize", type="llm_call", model="fake-llm") as summarize:
                summarize.output = "summary"
                summarize.tokens_input, summarize.tokens_output = 120, 30
                summarize.metadata["cached"] = False
            research.output = len(results["results"])
        run.output = {"answer": "summary"}
    assert results == {"results": ["q-0", "q-1"]}
    assert run.id is None  # nothing was sent yet: recording never waits for the network
    assert gw.flush() is True
    assert re.fullmatch(r"exe_[0-9a-f]{32}", run.id)

    assert sdk.posts("/agents") == [
        {
            "slug": "research-assistant",
            "name": "Research Assistant",
            "description": None,
            "framework": "custom",
            "metadata": {},
        }
    ]
    (created,) = sdk.posts("/executions")
    assert created["agent_id"] == "agt_" + "a" * 32
    assert (created["input"], created["tags"]) == ({"question": "q"}, ["t"])
    assert created["config"] == {"model": "m", "expected_steps": ["web_search"]}
    assert TIMESTAMP.fullmatch(created["started_at"])
    assert "replay_of" not in created and "replay_id" not in created

    events = sdk.events()
    assert [event["seq"] for event in events] == list(range(1, 11))
    assert all(TIMESTAMP.fullmatch(event["timestamp"]) for event in events)
    assert types(events) == [
        "step.started", "step.completed",  # plan
        "step.started",  # research
        "step.started", "step.completed",  # web_search
        "log",
        "step.started", "step.completed",  # summarize
        "step.completed",  # research
        "execution.completed",
    ]  # fmt: skip
    (
        plan_start,
        plan_end,
        research_start,
        search_start,
        search_end,
        log,
        llm_start,
        llm_end,
        research_end,
        done,
    ) = (event["payload"] for event in events)
    ids = {plan_start["step_id"], research_start["step_id"], search_start["step_id"], llm_start["step_id"]}
    assert len(ids) == 4 and all(STEP_ID.fullmatch(step_id) for step_id in ids)
    assert plan_start == {
        "step_id": plan_start["step_id"],
        "parent_step_id": None,
        "name": "plan",
        "step_type": "reasoning",
        "input": {"q": "q"},
        "tool_name": None,
        "model": None,
        "attempt": 1,
        "metadata": {},
    }
    assert plan_end == {
        "step_id": plan_start["step_id"],
        "output": {"queries": ["q"]},
        "tokens_input": None,
        "tokens_output": None,
        "metadata": {},
    }
    assert (research_start["parent_step_id"], research_start["step_type"], research_start["metadata"]) == (
        None,
        "custom",
        {"phase": 1},
    )
    assert search_start["parent_step_id"] == research_start["step_id"]
    assert (search_start["name"], search_start["step_type"], search_start["tool_name"]) == (
        "web_search",
        "tool_call",
        "web_search",
    )
    assert search_start["input"] == {"query": "q", "limit": 2}
    assert search_start["metadata"] == {"side_effects": False}
    assert search_end["output"] == {"results": ["q-0", "q-1"]}
    assert log == {"level": "info", "message": "searched", "step_id": research_start["step_id"]}
    assert (llm_start["parent_step_id"], llm_start["model"]) == (research_start["step_id"], "fake-llm")
    assert (llm_end["tokens_input"], llm_end["tokens_output"], llm_end["metadata"]) == (
        120,
        30,
        {"cached": False},
    )
    assert research_end["output"] == 2
    assert done == {"output": {"answer": "summary"}}


def test_exceptions_are_recorded_then_reraised_unchanged(sdk: StubApi) -> None:
    original = KeyError("results")
    with (
        pytest.raises(KeyError) as caught,
        gw.execution(input={}) as run,
        run.step("outer"),
        run.step("parse_results", type="reasoning") as inner,
    ):
        inner.output = {"partial": True}
        raise original
    assert caught.value is original
    gw.flush()

    events = sdk.events()
    assert types(events) == ["step.started", "step.started", "step.failed", "step.failed", "execution.failed"]
    inner_failed, outer_failed, execution_failed = (event["payload"] for event in events[2:])
    assert inner_failed["step_id"] == events[1]["payload"]["step_id"]
    assert outer_failed["step_id"] == events[0]["payload"]["step_id"]
    assert inner_failed["output"] == {"partial": True}
    for error in (inner_failed["error"], outer_failed["error"], execution_failed["error"]):
        assert (error["type"], error["message"]) == ("KeyError", "'results'")
        assert "Traceback (most recent call last)" in error["stacktrace"]
        assert "raise original" in error["stacktrace"]
    assert set(execution_failed) == {"error"}


def test_tool_calls_record_inputs_outputs_and_retry_attempts(sdk: StubApi) -> None:
    responses = iter([RuntimeError("429"), RuntimeError("429"), {"kb": "article"}, {"kb": "again"}])

    @gw.tool
    def retrieve_kb(topic: str) -> dict:
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    with gw.execution(input={}) as run:
        results = []
        for _ in range(3):
            try:
                results.append(retrieve_kb("billing"))
            except RuntimeError as exc:
                results.append(str(exc))
        results.append(retrieve_kb(topic="billing"))
        results.append(submit({"id": 17}))
        run.output = results
    assert results == ["429", "429", {"kb": "article"}, {"kb": "again"}, {"submitted": 17}]
    gw.flush()

    starts = [event["payload"] for event in sdk.events() if event["type"] == "step.started"]
    assert [(start["tool_name"], start["attempt"]) for start in starts] == [
        ("retrieve_kb", 1),
        ("retrieve_kb", 2),
        ("retrieve_kb", 3),
        ("retrieve_kb", 1),  # the previous call succeeded, so this is a fresh first attempt
        ("submit_invoice", 1),
    ]
    assert all(
        start["step_type"] == "tool_call" and start["input"] == {"topic": "billing"} for start in starts[:4]
    )
    assert starts[4]["input"] == {"invoice": {"id": 17}}
    assert starts[4]["metadata"] == {"side_effects": True}
    assert types(sdk.events())[1:6:2] == ["step.failed", "step.failed", "step.completed"]
    assert submit.__ghostwatch_tool__ == {"name": "submit_invoice", "side_effects": True}


def test_a_tool_called_with_bad_arguments_raises_the_normal_type_error(sdk: StubApi) -> None:
    with pytest.raises(TypeError, match="web_search"), gw.execution():
        web_search()  # type: ignore[call-arg]
    gw.flush()
    assert types(sdk.events()) == ["step.started", "step.failed", "execution.failed"]


def test_tools_run_normally_outside_an_execution(sdk: StubApi) -> None:
    assert web_search("x", 1) == {"results": ["x-0"]}
    assert gw.flush() is True
    assert sdk.requests == []


def test_unserialisable_values_never_break_the_agent(sdk: StubApi) -> None:
    class Opaque:
        def __repr__(self) -> str:
            return "<Opaque>"

    with gw.execution(input={"when": datetime(2026, 1, 1), 1: {"a", "b"}}) as run:
        with run.step("load") as step:
            step.output = {"blob": b"\x00\x01", "object": Opaque(), "items": (1, 2)}
        run.output = Opaque()
    assert gw.flush() is True
    (created,) = sdk.posts("/executions")
    assert created["input"]["when"] == repr(datetime(2026, 1, 1))
    assert sorted(created["input"]["1"]) == ["a", "b"]
    completed = sdk.events()[1]["payload"]
    assert completed["output"] == {"blob": repr(b"\x00\x01"), "object": "<Opaque>", "items": [1, 2]}
    assert sdk.events()[-1]["payload"] == {"output": "<Opaque>"}


def test_to_json() -> None:
    assert to_json({"a": [1, 2.5, None, True, "x"]}) == {"a": [1, 2.5, None, True, "x"]}
    assert to_json((1, {2})) == [1, [2]]
    assert to_json({1: object}) == {"1": repr(object)}
    assert to_json({"score": float("nan"), "limit": float("inf"), "ok": 1.5}) == {
        "score": "nan",
        "limit": "inf",
        "ok": 1.5,
    }


def test_invalid_step_type_is_a_programming_error(sdk: StubApi) -> None:
    with gw.execution() as run, pytest.raises(ValueError, match="step type"):
        run.step("x", type="thinking")


def test_fail_open_when_ghostwatch_is_unreachable(caplog: pytest.LogCaptureFixture) -> None:
    gw.init(
        agent=AGENT,
        api_url=closed_port_url(),
        api_key=API_KEY,
        flush_interval=0.05,
        batch_size=2,
        timeout=0.5,
    )
    started = time.monotonic()
    with caplog.at_level(logging.WARNING, logger="ghostwatch"), gw.execution(input={"q": 1}) as run:
        with run.step("plan") as step:
            step.output = 1
        answer = web_search("q", 1)
        run.output = answer
    elapsed = time.monotonic() - started
    assert answer == {"results": ["q-0"]}
    assert elapsed < 0.5, f"the agent was slowed down by {elapsed:.2f}s"
    with caplog.at_level(logging.WARNING, logger="ghostwatch"):
        assert gw.flush(timeout=1.0) is False
    assert any("unreachable" in record.message for record in caplog.records)
    assert run.id is None


def test_fail_open_when_ghostwatch_rejects_the_key(api: StubApi, caplog: pytest.LogCaptureFixture) -> None:
    gw.init(agent=AGENT, api_url=api.url, api_key="wrong-key", flush_interval=60, batch_size=10_000)
    with caplog.at_level(logging.WARNING, logger="ghostwatch"):
        with gw.execution() as run:
            assert web_search("q", 1) == {"results": ["q-0"]}
        assert gw.flush() is True  # nothing is left: the run was given up on, not retried forever
    assert api.requests == []
    assert any("HTTP 401" in record.message and "dropped" in record.message for record in caplog.records)
    assert run.id is None


def test_server_errors_are_retried_and_order_is_kept(sdk: StubApi) -> None:
    sdk.fail_next(2, 503)
    with gw.execution() as run:
        for index in range(3):
            with run.step(f"step-{index}"):
                pass
    assert gw.flush() is False  # first attempt hits a 503
    assert gw.flush() is False  # so does the second
    assert sdk.events() == []
    assert gw.flush() is True
    assert [event["seq"] for event in sdk.events()] == list(range(1, 8))
    assert len(sdk.posts("/executions")) == 1  # the execution was created once, not once per attempt
    assert gw.flush() is True
    assert len(sdk.events()) == 7  # and nothing is sent twice


def test_a_rejected_batch_stops_recording_that_run_only(
    sdk: StubApi, caplog: pytest.LogCaptureFixture
) -> None:
    sdk.fail_next(1, 422)
    with caplog.at_level(logging.WARNING, logger="ghostwatch"):
        with gw.execution() as rejected:
            with rejected.step("a"):
                pass
            assert gw.flush() is True  # the two events were dropped
            with rejected.step("b"):
                pass
        with gw.execution() as healthy, healthy.step("c"):
            pass
        assert gw.flush() is True
    assert [event["payload"].get("name") for event in sdk.events() if event["type"] == "step.started"] == [
        "c"
    ]
    assert any("stub failure 422" in record.message for record in caplog.records)


def test_events_are_sent_in_the_background_once_a_batch_is_full(api: StubApi) -> None:
    gw.init(agent=AGENT, api_url=api.url, api_key=API_KEY, flush_interval=60, batch_size=4)
    with gw.execution() as run:
        with run.step("one"), run.step("two"):
            assert api.events() == []  # two events queued, below the batch size
        assert wait_for(lambda: len(api.events()) == 4), api.events()
        assert [event["seq"] for event in api.events()] == [1, 2, 3, 4]
    assert wait_for(
        lambda: types(api.events())[-1:] == ["execution.completed"]
    )  # the terminal event is not held back


def test_events_are_sent_in_the_background_on_the_flush_interval(api: StubApi) -> None:
    gw.init(agent=AGENT, api_url=api.url, api_key=API_KEY, flush_interval=0.05, batch_size=10_000)
    with gw.execution() as run:
        with run.step("only"):
            pass
        assert wait_for(lambda: len(api.events()) == 2), api.events()
        assert run.id is not None


def test_large_runs_are_split_into_batches_of_at_most_500(sdk: StubApi) -> None:
    with gw.execution() as run:
        for index in range(600):
            run.log(f"line {index}")
    assert gw.flush() is True
    batches = [len(body["events"]) for body in sdk.posts("/events")]
    assert batches == [500, 101]
    assert [event["seq"] for event in sdk.events()] == list(range(1, 602))


def test_seq_is_unique_and_gapless_across_threads(sdk: StubApi) -> None:
    with gw.execution() as run:

        def work(name: str) -> None:
            for _ in range(25):
                with run.step(name):
                    pass

        threads = [threading.Thread(target=work, args=(f"worker-{index}",)) for index in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert gw.flush() is True
    assert [event["seq"] for event in sdk.events()] == list(range(1, 202))


def test_two_runs_share_one_agent_registration(sdk: StubApi) -> None:
    for _ in range(2):
        with gw.execution():
            pass
    assert gw.flush() is True
    assert len(sdk.posts("/agents")) == 1
    assert len(sdk.posts("/executions")) == 2
    assert len({path for path, _, _ in sdk.requests if path.endswith("/events")}) == 2


def test_replay_fields_are_sent_when_given(sdk: StubApi) -> None:
    with gw.execution(replay_of="exe_" + "1" * 32, replay_id="rpl_" + "2" * 32):
        pass
    gw.flush()
    (created,) = sdk.posts("/executions")
    assert (created["replay_of"], created["replay_id"]) == ("exe_" + "1" * 32, "rpl_" + "2" * 32)


def test_clock_controls_every_timestamp(api: StubApi) -> None:
    now = [datetime(2026, 11, 1, 9, 0, 0, tzinfo=timezone.utc)]

    def clock() -> datetime:
        now[0] += timedelta(milliseconds=250)
        return now[0]

    gw.init(agent=AGENT, api_url=api.url, api_key=API_KEY, flush_interval=60, batch_size=10_000, clock=clock)
    with gw.execution() as run, run.step("only"):
        pass
    gw.flush()
    assert api.posts("/executions")[0]["started_at"] == "2026-11-01T09:00:00.250Z"
    assert [event["timestamp"] for event in api.events()] == [
        "2026-11-01T09:00:00.500Z",
        "2026-11-01T09:00:00.750Z",
        "2026-11-01T09:00:01.000Z",
    ]


def test_without_init_the_agent_runs_and_nothing_is_recorded(
    api: StubApi, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="ghostwatch"):
        for _ in range(2):
            with gw.execution(input={}) as run, run.step("plan") as step:
                step.output = web_search("q", 1)
    assert step.output == {"results": ["q-0"]}
    assert gw.flush() is True
    assert api.requests == []
    assert [record.message for record in caplog.records].count(
        "Ghostwatch: execution() used before init(); the agent runs normally but nothing is recorded"
    ) == 1
