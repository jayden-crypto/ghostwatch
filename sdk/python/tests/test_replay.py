"""Replay: the sandbox rule (API contract §10) and the worker that claims and runs replays."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from conftest import AGENT, API_KEY, StubApi

import ghostwatch as gw
from ghostwatch.replay import RecordedCallError, ReplaySession, recorded_exception, replaying

EXE = "exe_" + "1" * 32
RPL = "rpl_" + "2" * 32
AGT = "agt_" + "a" * 32
TRUNCATED = {"_truncated": True, "preview": "{...", "original_bytes": 70_000}

calls: list[str] = []  # the decorated functions that really ran


class RateLimited(Exception):
    pass


@gw.tool(side_effects=False)
def web_search(query: str) -> dict:
    calls.append("web_search")
    return {"results": [f"live-{query}"]}


@gw.tool(side_effects=False)
def lookup(key: str) -> str:
    calls.append("lookup")
    return f"live-{key}"


@gw.tool(side_effects=True)
def submit_invoice(invoice: dict) -> dict:
    calls.append("submit_invoice")
    return {"submitted": invoice["id"]}


@gw.tool
def send_email(to: str) -> str:  # does not declare side_effects
    calls.append("send_email")
    return "sent"


@gw.llm_call(model="demo-llm")
def summarize(text: str) -> dict:
    calls.append("summarize")
    return {"text": text.upper(), "usage": {"input_tokens": 9, "output_tokens": 4}}


@pytest.fixture(autouse=True)
def no_calls() -> None:
    calls.clear()


def recorded(
    name: str, output: Any = None, *, error: dict | None = None, occurrence: int = 1, llm: bool = False
) -> dict:
    return {
        "step_name": name,
        "step_type": "llm_call" if llm else "tool_call",
        "tool_name": None if llm else name,
        "occurrence": occurrence,
        "input": {},
        "output": output,
        "error": error,
    }


def failure(type: str, message: str) -> dict:
    return {"type": type, "message": message, "stacktrace": None}


def claim(
    recorded_calls: list[dict], *, mode: str = "sandbox", authorized: bool = False, input: Any = None
) -> dict:
    return {
        "replay": {
            "id": RPL,
            "original_execution_id": EXE,
            "mode": mode,
            "status": "claimed",
            "side_effects_authorized": authorized,
        },
        "bundle": {
            "original_execution": {
                "id": EXE,
                "agent_id": AGT,
                "input": {"question": "q"} if input is None else input,
            },
            "recorded_calls": recorded_calls,
        },
    }


def replay(api: StubApi, the_claim: dict, handler: Any) -> list[str]:
    """Queue the replay on the stub and run a worker over it once."""
    api.add_replay(the_claim, AGENT.slug)
    worker = gw.ReplayWorker(api_url=api.url, api_key=API_KEY, timeout=2)
    worker.register(AGENT, handler)
    return worker.run_once()


def steps(api: StubApi) -> list[tuple[str, str | None, str]]:
    """(name, replay_source, how it ended) for every step, in start order."""
    ended = {
        event["payload"]["step_id"]: event["type"].removeprefix("step.")
        for event in api.events()
        if event["type"] in ("step.completed", "step.failed")
    }
    return [
        (
            event["payload"]["name"],
            event["payload"]["metadata"].get("replay_source"),
            ended[event["payload"]["step_id"]],
        )
        for event in api.events()
        if event["type"] == "step.started"
    ]


def step_errors(api: StubApi) -> list[tuple[str, str]]:
    return [
        (event["payload"]["error"]["type"], event["payload"]["error"]["message"])
        for event in api.events()
        if event["type"] == "step.failed"
    ]


def test_sandbox_serves_recordings_and_runs_only_what_is_safe(api: StubApi) -> None:
    seen = {}

    def agent(input: dict) -> None:
        with gw.execution(input=input, tags=["demo"]) as run:
            with run.step("plan", type="reasoning") as plan:
                plan.output = "plan"
            seen["search"] = web_search("q")
            seen["summary"] = summarize("fixed")
            run.output = seen["summary"]["text"]

    the_claim = claim([recorded("web_search", {"data": ["recorded"], "meta": {}})])
    assert replay(api, the_claim, agent) == [RPL]

    assert seen["search"] == {"data": ["recorded"], "meta": {}}  # the recording, not the live answer
    assert calls == ["summarize"]  # web_search was never called; summarize had no recording and is safe
    (created,) = api.posts("/executions")
    assert (created["replay_of"], created["replay_id"]) == (EXE, RPL)
    assert created["input"] == {"question": "q"}  # the original execution's input
    assert steps(api) == [
        ("plan", "executed", "completed"),
        ("web_search", "recorded", "completed"),
        ("summarize", "executed", "completed"),
    ]
    assert api.events()[-1]["type"] == "execution.completed"
    assert api.replays[RPL]["status"] == "claimed"
    assert len(api.posts(f"/replays/{RPL}/claim")) == 1


@pytest.mark.parametrize(
    ("unsafe_tool", "argument"), [(submit_invoice, {"id": 7}), (send_email, "a@example.test")]
)
def test_sandbox_never_runs_an_unrecorded_tool_that_may_have_side_effects(
    api: StubApi, unsafe_tool: Any, argument: Any
) -> None:
    def agent(input: dict) -> None:
        with gw.execution(input=input):
            web_search("q")
            unsafe_tool(argument)

    replay(api, claim([recorded("web_search", {"results": []})]), agent)

    name = unsafe_tool.__ghostwatch_tool__["name"]
    assert calls == []
    assert steps(api) == [("web_search", "recorded", "completed"), (name, "blocked", "failed")]
    ((error_type, message),) = step_errors(api)
    assert error_type == "SandboxRecordingMissing"
    assert message == (
        f"{name} has no recording for call 1 (the original execution made 0) "
        "and is not declared side_effects=False, so it is not run in a sandbox replay"
    )
    failed = api.events()[-1]
    assert (failed["type"], failed["payload"]["error"]["type"]) == (
        "execution.failed",
        "SandboxRecordingMissing",
    )


def test_a_recorded_side_effecting_tool_is_served_and_never_called(api: StubApi) -> None:
    seen = {}

    def agent(input: dict) -> None:
        with gw.execution(input=input):
            seen["first"] = submit_invoice({"id": 7})
            seen["second"] = submit_invoice({"id": 8})

    replay(api, claim([recorded("submit_invoice", {"submitted": "recorded-7"})]), agent)

    assert seen == {"first": {"submitted": "recorded-7"}}  # the second call was blocked, not run
    assert calls == []
    assert steps(api) == [
        ("submit_invoice", "recorded", "completed"),
        ("submit_invoice", "blocked", "failed"),
    ]
    assert step_errors(api)[0][1].startswith(
        "submit_invoice has no recording for call 2 (the original execution made 1)"
    )


def test_calls_are_matched_to_recordings_in_order_and_extra_safe_calls_run(api: StubApi) -> None:
    seen = []

    def agent(input: dict) -> None:
        with gw.execution(input=input):
            seen.extend(lookup(key) for key in ("a", "b", "c"))
            seen.append(web_search("q"))

    recordings = [
        recorded("lookup", "second", occurrence=2),
        recorded("lookup", "first", occurrence=1),
        recorded("web_search", {"results": ["recorded"]}),
    ]
    replay(api, claim(recordings), agent)

    assert seen == ["first", "second", "live-c", {"results": ["recorded"]}]
    assert calls == ["lookup"]
    assert [source for _, source, _ in steps(api)] == ["recorded", "recorded", "executed", "recorded"]


def test_a_recorded_failure_is_raised_again_as_the_same_exception_class(api: StubApi) -> None:
    seen = []

    def agent(input: dict) -> None:
        with gw.execution(input=input) as run:
            for _ in range(2):
                try:
                    seen.append(web_search("q"))
                except RateLimited as exc:  # the agent's own retry logic still works on a replay
                    seen.append(f"retry after {exc}")
            try:
                lookup("k")
            except KeyError as exc:
                seen.append(exc.args)
            run.output = seen[1]

    recordings = [
        recorded("web_search", error=failure("RateLimited", "HTTP 429"), occurrence=1),
        recorded("web_search", {"results": ["recorded"]}, occurrence=2),
        recorded("lookup", error=failure("KeyError", "'results'")),
    ]
    replay(api, claim(recordings), agent)

    assert seen == ["retry after HTTP 429", {"results": ["recorded"]}, ("results",)]
    assert calls == []
    assert steps(api) == [
        ("web_search", "recorded", "failed"),
        ("web_search", "recorded", "completed"),
        ("lookup", "recorded", "failed"),
    ]
    assert step_errors(api) == [("RateLimited", "HTTP 429"), ("KeyError", "'results'")]
    starts = [event["payload"] for event in api.events() if event["type"] == "step.started"]
    assert [start["attempt"] for start in starts] == [1, 2, 1]
    assert api.events()[-1]["type"] == "execution.completed"


def test_recorded_exception_keeps_the_class_name_when_the_class_is_unknown() -> None:
    error = recorded_exception(failure("UpstreamTimeout", "no answer in 30 s"), web_search)
    assert isinstance(error, RecordedCallError)
    assert (type(error).__name__, str(error)) == ("UpstreamTimeout", "no answer in 30 s")

    known = recorded_exception(failure("RateLimited", "HTTP 429"), web_search)
    assert type(known) is RateLimited and str(known) == "HTTP 429"
    builtin = recorded_exception(failure("ValueError", "bad total"), web_search)
    assert type(builtin) is ValueError and str(builtin) == "bad total"
    # A name that is not an exception class (here, a function in the module) is never instantiated.
    not_a_class = recorded_exception(failure("failure", "x"), web_search)
    assert isinstance(not_a_class, RecordedCallError)


def test_a_truncated_recording_is_blocked_instead_of_served(api: StubApi) -> None:
    def agent(input: dict) -> None:
        with gw.execution(input=input):
            web_search("q")

    replay(api, claim([recorded("web_search", TRUNCATED)]), agent)

    assert calls == []  # not run either: the run must not silently differ from the recording
    assert steps(api) == [("web_search", "blocked", "failed")]
    assert step_errors(api) == [
        (
            "SandboxRecordingMissing",
            "the recorded output of web_search (call 1) was larger than 64 KB and only a preview of it "
            "was stored, so it cannot be served",
        )
    ]


def test_a_served_llm_recording_reports_no_tokens_for_this_run(api: StubApi) -> None:
    seen = {}

    def agent(input: dict) -> None:
        with gw.execution(input=input):
            seen["summary"] = summarize("text")

    output = {"text": "RECORDED", "usage": {"input_tokens": 500, "output_tokens": 80}}
    replay(api, claim([recorded("summarize", output, llm=True)]), agent)

    assert seen["summary"] == output and calls == []
    completed = next(event["payload"] for event in api.events() if event["type"] == "step.completed")
    assert (completed["tokens_input"], completed["tokens_output"]) == (None, None)
    assert steps(api) == [("summarize", "recorded", "completed")]


def test_an_authorized_live_replay_runs_everything_for_real(api: StubApi) -> None:
    def agent(input: dict) -> None:
        with gw.execution(input=input):
            web_search("q")
            submit_invoice({"id": 7})
            summarize("text")

    recordings = [recorded("web_search", {"results": ["recorded"]}), recorded("submit_invoice", {})]
    replay(api, claim(recordings, mode="live", authorized=True), agent)

    assert calls == ["web_search", "submit_invoice", "summarize"]
    assert [source for _, source, _ in steps(api)] == ["executed", "executed", "executed"]


@pytest.mark.parametrize(
    ("the_claim", "reason"),
    [
        (
            claim([], mode="live", authorized=False),
            "a live replay needs side-effect authorization, and this one does not have it",
        ),
        (
            claim([], input=TRUNCATED),
            "the original input was larger than 64 KB and only a preview of it was stored",
        ),
    ],
)
def test_a_replay_that_cannot_be_faithful_fails_without_running_the_agent(
    api: StubApi, the_claim: dict, reason: str
) -> None:
    ran = []
    assert replay(api, the_claim, ran.append) == [RPL]

    assert ran == [] and calls == []
    (created,) = api.posts("/executions")
    assert (created["replay_of"], created["replay_id"]) == (EXE, RPL)
    (event,) = api.events()
    assert event["type"] == "execution.failed"
    assert (event["payload"]["error"]["type"], event["payload"]["error"]["message"]) == (
        "ReplayNotPossible",
        reason,
    )


def test_only_the_first_execution_a_handler_opens_is_the_replay(api: StubApi) -> None:
    def agent(input: dict) -> None:
        with gw.execution(input=input):
            web_search("q")
        with gw.execution(input={"follow": "up"}):
            web_search("q")

    replay(api, claim([recorded("web_search", {"results": ["recorded"]})]), agent)

    first, second = api.posts("/executions")
    assert first["replay_id"] == RPL
    assert "replay_id" not in second and "replay_of" not in second
    assert calls == ["web_search"]  # the second execution is an ordinary run
    starts = [event["payload"]["metadata"] for event in api.events() if event["type"] == "step.started"]
    assert starts == [{"side_effects": False, "replay_source": "recorded"}, {"side_effects": False}]


def test_an_agent_that_raises_does_not_stop_the_worker(
    api: StubApi, caplog: pytest.LogCaptureFixture
) -> None:
    def agent(input: dict) -> None:
        with gw.execution(input=input):
            raise ValueError("still broken")

    with caplog.at_level(logging.INFO, logger="ghostwatch"):
        assert replay(api, claim([]), agent) == [RPL]
    assert api.events()[-1]["type"] == "execution.failed"
    assert any("the agent raised ValueError: still broken" in record.message for record in caplog.records)


def test_the_worker_leaves_other_agents_replays_and_lost_claims_alone(api: StubApi) -> None:
    ran = []
    api.add_replay(claim([]), "someone-elses-agent")
    worker = gw.ReplayWorker(api_url=api.url, api_key=API_KEY, timeout=2)
    worker.register(AGENT, ran.append)
    assert worker.run_once() == []
    assert api.posts(f"/replays/{RPL}/claim") == []  # never claimed: another worker has that code
    assert api.replays[RPL]["status"] == "pending"

    # Ours, but another worker claims it between the poll and the claim: skipped, not an error.
    api.replays[RPL]["agent_slug"] = AGENT.slug
    original_read = api._read

    def claimed_meanwhile(path: str) -> tuple[int, dict]:
        response = original_read(path)
        if path.startswith("/agents/"):
            api.replays[RPL]["status"] = "claimed"
        return response

    api._read = claimed_meanwhile  # type: ignore[method-assign]
    assert worker.run_once() == []
    assert ran == [] and api.posts("/executions") == []


def test_outside_a_worker_a_session_applies_to_the_next_execution_only(sdk: StubApi) -> None:
    session = ReplaySession(claim([recorded("web_search", {"results": ["recorded"]})]))
    with replaying(session):
        with gw.execution(input={}) as run:
            assert web_search("q") == {"results": ["recorded"]}
        assert run.replay is session
    with gw.execution(input={}) as later:
        assert web_search("q") == {"results": ["live-q"]}
    assert later.replay is None
