"""The demo (demo/) against the real API: seeded history and the injected failure scenarios.

Everything asserted here was produced by the backend from events the demo agents sent through the
SDK. The demo never touches the database.
"""

import importlib
import json
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx2
import pytest

from app.config import REPO_ROOT, get_settings
from app.schemas.agents import Agent
from app.schemas.anomalies import Anomaly
from app.schemas.common import Page
from app.schemas.executions import ExecutionSummary
from app.schemas.investigations import Investigation
from app.schemas.replays import Replay
from app.schemas.stats import StatsTimeseries
from app.schemas.traces import Trace
from tests.test_conformance import validate

DEMO_DIR = REPO_ROOT / "demo"


@pytest.fixture
def demo(live_api: str, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """The demo's modules, configured to talk to the test server."""
    monkeypatch.syspath_prepend(str(DEMO_DIR))
    monkeypatch.setenv("GHOSTWATCH_API_URL", live_api)
    monkeypatch.setenv("GHOSTWATCH_API_KEY", get_settings().ghostwatch_api_key)
    names = ("seed", "run_scenario", "runner", "scenarios", "replay")
    modules = SimpleNamespace(**{name: importlib.import_module(name) for name in names})
    modules.timing = importlib.import_module("fake_services.timing").timing
    modules.invoices = importlib.import_module("agents.invoice_processor").invoices
    modules.invoices.submitted.clear()
    modules.research = importlib.import_module("agents.research_assistant")
    modules.http = httpx2.Client(base_url=live_api)
    yield modules
    modules.http.close()
    modules.research.PARSER_FIX_DEPLOYED = False
    modules.timing.use_real_time()
    modules.scenarios.reset_services()


def get(demo: SimpleNamespace, schema: object, path: str) -> object:
    return validate(schema, demo.http.get(path).content)


def trace_of(demo: SimpleNamespace, execution_id: str) -> Trace:
    return get(demo, Trace, f"/executions/{execution_id}/trace")


def test_seed_builds_a_week_of_history_through_the_sdk(demo: SimpleNamespace) -> None:
    now = datetime.now(UTC)
    assert demo.seed.seed(runs_per_agent=6, now=now) == 6 * 3 + 2

    executions = get(demo, Page[ExecutionSummary], "/executions?limit=200&sort=started_at")
    assert executions.total == 20
    assert {item.status for item in executions.items} == {"completed"}
    assert now - timedelta(days=6) <= executions.items[0].started_at <= now - timedelta(days=5, hours=23)
    assert executions.items[-1].started_at < now  # nothing is dated in the future
    assert all(item.duration_ms > 0 and item.step_count >= 3 for item in executions.items)

    agents = {agent.slug: agent.stats for agent in get(demo, Page[Agent], "/agents").items}
    assert {slug: stats.health for slug, stats in agents.items()} == {
        "research-assistant": "healthy",
        "invoice-processor": "healthy",
        "support-triage": "degraded",
    }
    assert {slug: stats.total_executions for slug, stats in agents.items()} == {
        "research-assistant": 6,
        "invoice-processor": 6,
        "support-triage": 8,
    }
    assert all(stats.success_rate == 1.0 for stats in agents.values())

    anomalies = get(demo, Page[Anomaly], "/anomalies").items
    assert sorted((a.type, a.severity, a.agent_name) for a in anomalies) == [
        ("duration_spike", "high", "Support Triage"),
        ("excessive_retries", "medium", "Support Triage"),
    ]

    series = get(demo, StatsTimeseries, "/stats/timeseries?window=7d")
    assert sum(point.completed for point in series.points) == 20
    assert sum(1 for point in series.points if point.completed) >= 5  # spread over the week, not one day

    research = [item for item in executions.items if item.agent_name == "Research Assistant"]
    for item in research:
        steps = trace_of(demo, item.id).steps
        assert [step.name for step in steps] == ["plan", "web_search", "parse_results", "summarize"]
        assert [step.type for step in steps] == ["reasoning", "tool_call", "reasoning", "llm_call"]
    assert all(item.tokens_total and item.cost_usd is None for item in research)  # demo-llm-1 has no price
    durations = sorted(item.duration_ms for item in research)
    assert durations[0] != durations[-1] and durations[-1] < 1.5 * durations[0]  # varied, but no outliers


def test_seed_with_failures_adds_the_two_demo_incidents(demo: SimpleNamespace) -> None:
    assert demo.seed.seed(runs_per_agent=5, include_failures=True) == 5 * 3 + 4

    failed = get(demo, Page[ExecutionSummary], "/executions?status=failed").items
    assert [(item.agent_name, item.error.type, item.error.message) for item in failed] == [
        ("Research Assistant", "KeyError", "'results'")
    ]
    ghost = get(demo, Page[Anomaly], "/anomalies?type=ghost_completion").items
    assert [(a.severity, a.agent_name, a.title) for a in ghost] == [
        ("critical", "Invoice Processor", "Reported completed, but submit_invoice never completed")
    ]
    health = {agent.slug: agent.stats.health for agent in get(demo, Page[Agent], "/agents").items}
    assert health["invoice-processor"] == "failing"


def test_schema_change_scenario_fails_on_the_missing_key(demo: SimpleNamespace) -> None:
    result = demo.run_scenario.run("schema-change")
    assert isinstance(result.error, KeyError) and result.error.args == ("results",)
    assert result.output is None

    trace = trace_of(demo, result.execution.id)
    assert (trace.execution.status, trace.execution.error.type, trace.execution.error.message) == (
        "failed",
        "KeyError",
        "'results'",
    )
    plan, search, parse = trace.steps
    assert [step.status for step in trace.steps] == ["completed", "completed", "failed"]
    # The evidence an investigation needs: the tool's output has no "results" key, and the next
    # step asked for it.
    assert sorted(search.output) == ["data", "meta"]
    assert (parse.name, parse.error.type, parse.error.message) == ("parse_results", "KeyError", "'results'")
    assert 'payload["results"]' in parse.error.stacktrace

    # Ghostwatch investigates the failure on its own and confirms the root cause from the evidence.
    investigation = demo.run_scenario.wait_for_investigation(result.execution.id)
    validate(Investigation, json.dumps(investigation))
    assert (investigation["status"], investigation["trigger"], investigation["provider"]) == (
        "completed",
        "auto_failure",
        "rule_based",
    )
    report = investigation["report"]
    assert (report["root_cause"]["status"], report["root_cause"]["signature"]) == (
        "confirmed",
        "missing_key_in_upstream_output",
    )
    assert report["root_cause"]["statement"] == (
        "Step 3 parse_results read the key 'results', which the output of Step 2 web_search (tool web_search) "
        "does not contain. That output's keys are: data, meta."
    )
    assert report["failing_step_id"] == parse.id
    assert report["relevant_step_ids"] == [search.id, parse.id]  # one click from the claim to the proof
    assert plan.output == {"query": "how do teams trace what an ai agent did"}


def test_ghost_invoice_scenario_reports_success_without_submitting(
    demo: SimpleNamespace, capsys: pytest.CaptureFixture
) -> None:
    healthy = demo.run_scenario.run("healthy", "invoice-processor")
    assert healthy.output == {"status": "processed", "invoice_number": "INV-2041"}
    assert demo.invoices.submitted == ["INV-2041"]  # the side effect really happened

    result = demo.run_scenario.run("ghost-invoice")
    assert result.error is None
    assert result.output == {"status": "processed", "invoice_number": "INV-2042"}  # the agent says it worked
    assert demo.invoices.submitted == ["INV-2041"]  # but nothing was submitted

    trace = trace_of(demo, result.execution.id)
    assert trace.execution.status == "completed"
    assert [step.name for step in trace.steps] == ["extract_fields", "validate"]
    (anomaly,) = trace.anomalies
    assert (anomaly.type, anomaly.severity) == ("ghost_completion", "critical")
    assert anomaly.evidence[0].expected == ["extract_fields", "validate", "submit_invoice"]

    healthy_steps = trace_of(demo, healthy.execution.id).steps
    assert [step.name for step in healthy_steps] == ["extract_fields", "validate", "submit_invoice"]
    assert healthy_steps[2].metadata == {"side_effects": True}
    assert trace_of(demo, healthy.execution.id).anomalies == []

    investigation = demo.run_scenario.wait_for_investigation(result.execution.id)
    assert (investigation["trigger"], investigation["report"]["root_cause"]["signature"]) == (
        "auto_anomaly",
        "ghost_completion",
    )
    assert investigation["report"]["root_cause"]["status"] == "confirmed"

    demo.run_scenario.report(result)
    printed = capsys.readouterr().out
    assert "investigation: confirmed (signature ghost_completion), provider rule_based" in printed
    assert "Agent result : returned {'status': 'processed'" in printed
    assert "[critical] ghost_completion" in printed
    assert f"/executions/{result.execution.id}" in printed


def comparable(trace: Trace) -> list[tuple]:
    """A trace without its ids and timestamps: what must be identical between two runs of a scenario."""
    return [
        (step.ordinal, step.depth, step.name, step.type, step.status, step.attempt, step.input, step.output,
         step.tool_name, step.model, step.tokens_input, step.tokens_output, step.duration_ms,
         (step.error.type, step.error.message) if step.error else None)
        for step in trace.steps
    ]  # fmt: skip


@pytest.mark.parametrize("name", ["rate-limit", "slow", "schema-change", "ghost-invoice"])
def test_a_scenario_is_identical_every_time_it_runs(demo: SimpleNamespace, name: str) -> None:
    scenario = demo.scenarios.SCENARIOS[name]
    demo.runner.use_agent(scenario.agent, clock=demo.timing.now)
    traces = []
    for _ in range(2):
        demo.timing.use_simulated_time(datetime(2026, 11, 14, 9, 0, tzinfo=UTC))
        result = demo.runner.run_agent(scenario.agent, scenario.input, disturb=scenario.disturb, seed=1000)
        assert demo.runner.gw.flush() is True
        traces.append(trace_of(demo, result.execution.id))
    first, second = traces
    assert comparable(first) == comparable(second)
    assert (first.execution.status, first.execution.duration_ms, first.execution.output) == (
        second.execution.status, second.execution.duration_ms, second.execution.output,
    )  # fmt: skip
    assert first.execution.id != second.execution.id


def test_rate_limit_scenario_retries_and_is_flagged(demo: SimpleNamespace) -> None:
    demo.runner.use_agent("support-triage", clock=demo.timing.now)
    demo.timing.use_simulated_time(datetime(2026, 11, 14, 9, 0, tzinfo=UTC))
    scenario = demo.scenarios.SCENARIOS["rate-limit"]
    result = demo.runner.run_agent(scenario.agent, scenario.input, disturb=scenario.disturb)
    assert demo.runner.gw.flush() is True
    assert result.output["category"] == "billing" and result.error is None

    trace = trace_of(demo, result.execution.id)
    assert [(step.name, step.attempt, step.status) for step in trace.steps] == [
        ("classify", 1, "completed"),
        ("retrieve_kb", 1, "failed"),
        ("retrieve_kb", 2, "failed"),
        ("retrieve_kb", 3, "completed"),
        ("draft_reply", 1, "completed"),
    ]
    assert [(a.type, a.title) for a in trace.anomalies] == [
        ("excessive_retries", "2 retried steps, highest attempt 3")
    ]


def replay_in_sandbox(demo: SimpleNamespace, execution_id: str, *, fixed: bool) -> Replay:
    """Request a sandbox replay as the dashboard does, let a demo worker run it, and read it back."""
    response = demo.http.post(f"/executions/{execution_id}/replay", json={"mode": "sandbox"})
    assert response.status_code == 201, response.text
    replay_id = response.json()["id"]
    assert demo.replay.build_worker(fixed=fixed).run_once() == [replay_id]
    return get(demo, Replay, f"/replays/{replay_id}")


def diffs(replay: Replay) -> list[tuple]:
    return [
        (diff.name, diff.change, diff.original_status, diff.replay_status, diff.replay_source)
        for diff in replay.comparison.step_diffs
    ]


def test_replaying_the_schema_change_failure_is_fixed_only_once_the_parser_is(demo: SimpleNamespace) -> None:
    failed = demo.run_scenario.run("schema-change")
    assert isinstance(failed.error, KeyError)

    # The agent as it shipped: the recorded search response breaks it in exactly the same way.
    unfixed = replay_in_sandbox(demo, failed.execution.id, fixed=False)
    assert (unfixed.status, unfixed.comparison.outcome) == ("completed", "same_failure")
    assert diffs(unfixed) == [
        ("plan", "unchanged", "completed", "completed", "executed"),
        ("web_search", "unchanged", "completed", "completed", "recorded"),
        ("parse_results", "unchanged", "failed", "failed", "executed"),
    ]

    # With the fix deployed, the same recorded response is parsed and the run completes.
    fixed = replay_in_sandbox(demo, failed.execution.id, fixed=True)
    assert (fixed.status, fixed.mode, fixed.side_effects_authorized) == ("completed", "sandbox", False)
    assert fixed.comparison.outcome == "fixed"
    assert (fixed.comparison.original.status, fixed.comparison.replay.status) == ("failed", "completed")
    assert diffs(fixed) == [
        ("plan", "unchanged", "completed", "completed", "executed"),
        ("web_search", "unchanged", "completed", "completed", "recorded"),
        ("parse_results", "status_changed", "failed", "completed", "executed"),
        ("summarize", "added", None, "completed", "executed"),  # no recording: a model call may run
    ]
    assert fixed.comparison.step_count_delta == 1

    original, replayed = trace_of(demo, failed.execution.id), trace_of(demo, fixed.replay_execution_id)
    assert (replayed.execution.replay_of, replayed.execution.status) == (failed.execution.id, "completed")
    assert replayed.execution.input == original.execution.input
    # web_search was served the recording byte for byte: the new response shape, not a live v1 answer.
    assert replayed.steps[1].output == original.steps[1].output
    assert sorted(replayed.steps[1].output) == ["data", "meta"]
    assert [step.metadata["replay_source"] for step in replayed.steps] == [
        "executed", "recorded", "executed", "executed",
    ]  # fmt: skip
    assert replayed.execution.output["sources"] == [hit["title"] for hit in original.steps[1].output["data"]]

    listed = get(demo, Page[Replay], f"/replays?original_execution_id={failed.execution.id}")
    assert [item.id for item in listed.items] == [fixed.id, unfixed.id]


def test_a_sandbox_replay_never_submits_an_invoice(demo: SimpleNamespace) -> None:
    healthy = demo.run_scenario.run("healthy", "invoice-processor")
    assert demo.invoices.submitted == ["INV-2041"]

    # The original run submitted the invoice, so the replay is served that recording.
    replay = replay_in_sandbox(demo, healthy.execution.id, fixed=False)
    assert demo.invoices.submitted == ["INV-2041"]  # not submitted a second time
    assert replay.comparison.outcome == "both_succeeded"
    assert diffs(replay)[-1] == ("submit_invoice", "unchanged", "completed", "completed", "recorded")

    # The ghost run never reached submit_invoice. Replayed now that validation is back up, the agent
    # does reach it, there is no recording, and the sandbox blocks the call instead of running it.
    ghost = demo.run_scenario.run("ghost-invoice")
    replay = replay_in_sandbox(demo, ghost.execution.id, fixed=False)
    assert demo.invoices.submitted == ["INV-2041"]
    assert diffs(replay)[-1] == ("submit_invoice", "added", None, "failed", "blocked")
    assert replay.comparison.outcome == "regressed"
    blocked = trace_of(demo, replay.replay_execution_id).steps[-1]
    assert (blocked.error.type, blocked.metadata) == (
        "SandboxRecordingMissing",
        {"side_effects": True, "replay_source": "blocked"},
    )


def test_the_demo_never_touches_the_database() -> None:
    forbidden = re.compile(r"^\s*(from|import)\s+(sqlalchemy|psycopg|alembic|app)\b|DATABASE_URL", re.M)
    sources = [path for path in DEMO_DIR.rglob("*.py") if ".venv" not in path.parts]
    assert len(sources) >= 10
    for path in sources:
        assert not forbidden.search(path.read_text()), (
            f"{path.relative_to(REPO_ROOT)} reaches for the database"
        )
