"""Contract §8: each rule fires when it should, stays quiet when it should not, and says exactly why."""

from typing import Any

import pytest

from app.models import Execution, Step
from app.schemas.anomalies import Anomaly as AnomalySchema
from app.services.anomaly import rules
from app.services.anomaly.baseline import Baseline, RecentRun, percentile_95
from app.services.anomaly.rules import AnomalyDraft, RuleInput, StaleInfo
from tests.factories import T0

EXECUTION_ID = "exe_" + "e" * 32
# 20 completed runs: durations 9,000..10,900 ms (median 9,950, p95 10,800); tokens 1,000..1,190.
BASELINE = Baseline(
    durations_ms=[9000 + 100 * index for index in range(20)],
    token_totals=[1000 + 10 * index for index in range(20)],
    step_counts=[4] * 19 + [5],
    tool_names=frozenset({"web_search"}),
)
THIN_BASELINE = Baseline(
    durations_ms=[100] * 4, token_totals=[10] * 4, step_counts=[2] * 4, tool_names=frozenset()
)


def execution(status: str = "completed", **values: Any) -> Execution:
    defaults = {"id": EXECUTION_ID, "status": status, "config": {}, "step_count": 0, "started_at": T0}
    return Execution(**{**defaults, **values})


def step(ordinal: int, name: str = "work", status: str = "completed", **values: Any) -> Step:
    return Step(
        id=f"stp_{ordinal:032x}", ordinal=ordinal, name=name, type="custom", status=status,
        attempt=values.pop("attempt", 1), **values,
    )  # fmt: skip


def failed_tool_step(ordinal: int, tool: str = "retrieve_kb", attempt: int = 1) -> Step:
    error = {"type": "HTTPError", "message": "429 Too Many Requests", "stacktrace": None}
    return step(ordinal, tool, "failed", tool_name=tool, attempt=attempt, error=error)


def rule_input(
    run: Execution,
    steps: list[Step] | None = None,
    baseline: Baseline = BASELINE,
    recent: list[RecentRun] | None = None,
    stale: StaleInfo | None = None,
) -> RuleInput:
    steps = steps or []
    run.step_count = run.step_count or len(steps)
    this_run = RecentRun(
        run.id, run.status, frozenset(s.tool_name for s in steps if s.status == "failed" and s.tool_name)
    )
    return RuleInput(run, steps, baseline, [this_run, *(recent or [])], "research-assistant", stale)


def earlier(number: int, status: str = "completed", failed_tools: tuple[str, ...] = ()) -> RecentRun:
    return RecentRun(f"exe_{number:032x}", status, frozenset(failed_tools))


def assert_well_formed(draft: AnomalyDraft, anomaly_type: str, severity: str) -> None:
    """Every draft must be a valid contract Anomaly: >= 1 evidence item, title <= 80 chars, real ids."""
    assert (draft.type, draft.severity, draft.rule_id) == (anomaly_type, severity, f"{anomaly_type}.v1")
    AnomalySchema.model_validate(
        {
            "id": "anm_" + "a" * 32,
            "type": draft.type,
            "severity": draft.severity,
            "status": "open",
            "agent_id": "agt_" + "a" * 32,
            "agent_name": "Research Assistant",
            "execution_id": EXECUTION_ID,
            "detected_at": T0,
            "rule_id": draft.rule_id,
            "title": draft.title,
            "explanation": draft.explanation,
            "evidence": draft.evidence,
        }
    )


def test_percentile_95_is_nearest_rank() -> None:
    assert percentile_95(list(range(1, 21))) == 19
    assert percentile_95(list(range(1, 101))) == 95
    assert percentile_95([7]) == 7
    assert percentile_95([5, 1, 3, 2, 4]) == 5
    assert (BASELINE.duration_median, BASELINE.duration_p95) == (9950, 10800)
    assert (BASELINE.token_median, BASELINE.token_p95, BASELINE.max_step_count) == (1095, 1180, 5)


# duration_spike: threshold = max(3 x 9,950, 1.5 x 10,800) = 29,850 ms; high above 5 x 9,950 = 49,750 ms.


def test_duration_spike_fires_above_the_threshold() -> None:
    draft = rules.duration_spike(rule_input(execution(duration_ms=41250)))
    assert_well_formed(draft, "duration_spike", "medium")
    assert draft.title == "Duration 4.1× above baseline"
    assert draft.explanation == (
        "Execution took 41,250 ms. Baseline median for research-assistant is 9,950 ms over 20 runs "
        "(p95 10,800 ms). Rule fires above max(3× median, 1.5× p95) = 29,850 ms. "
        "Severity is high above 5× median = 49,750 ms."
    )
    this_run, baseline = draft.evidence
    assert (this_run["kind"], this_run["ref_id"], this_run["field"]) == (
        "execution",
        EXECUTION_ID,
        "duration_ms",
    )
    assert (this_run["observed"], this_run["expected"]) == (41250, 29850)
    assert (baseline["kind"], baseline["ref_id"]) == ("baseline", None)
    assert baseline["observed"] == {"median": 9950, "p95": 10800, "runs": 20}


@pytest.mark.parametrize(
    ("duration", "expected"),
    [(29850, None), (29851, "medium"), (49750, "medium"), (49751, "high"), (9000, None), (None, None)],
)
def test_duration_spike_boundaries(duration: int | None, expected: str | None) -> None:
    draft = rules.duration_spike(rule_input(execution(duration_ms=duration)))
    assert (draft.severity if draft else None) == expected


def test_duration_spike_uses_p95_when_it_is_the_larger_bound() -> None:
    spread = Baseline(durations_ms=[100] * 18 + [1000, 1000], step_counts=[1] * 20)  # median 100, p95 1,000
    assert rules.duration_spike(rule_input(execution(duration_ms=1500), baseline=spread)) is None
    draft = rules.duration_spike(rule_input(execution(duration_ms=1501), baseline=spread))
    assert "max(3× median, 1.5× p95) = 1,500 ms" in draft.explanation
    assert draft.severity == "high"  # far above 5 x median


def test_baseline_rules_are_skipped_below_five_runs() -> None:
    wild = execution(duration_ms=10**9, tokens_input=10**9, step_count=500)
    steps = [step(1, "new_tool", tool_name="new_tool")]
    for rule in (rules.duration_spike, rules.token_spike, rules.unexpected_pattern):
        assert rule(rule_input(wild, steps, baseline=THIN_BASELINE)) is None
        assert rule(rule_input(wild, steps, baseline=Baseline())) is None
    five = Baseline(durations_ms=[100] * 5, token_totals=[10] * 5, step_counts=[2] * 5)
    assert rules.duration_spike(rule_input(wild, baseline=five)) is not None


# token_spike: threshold = max(2 x 1,095, 1,180) = 2,190 tokens; high above 4 x 1,095 = 4,380.


def test_token_spike_fires_above_the_threshold() -> None:
    draft = rules.token_spike(rule_input(execution(tokens_input=2500, tokens_output=500)))
    assert_well_formed(draft, "token_spike", "medium")
    assert draft.title == "Token usage 2.7× above baseline"
    assert draft.explanation == (
        "Execution used 3,000 tokens. Baseline median for research-assistant is 1,095 tokens over 20 runs "
        "(p95 1,180 tokens). Rule fires above max(2× median, p95) = 2,190 tokens. "
        "Severity is high above 4× median = 4,380 tokens."
    )
    assert (draft.evidence[0]["field"], draft.evidence[0]["observed"], draft.evidence[0]["expected"]) == (
        "tokens_total",
        3000,
        2190,
    )


@pytest.mark.parametrize(
    ("tokens", "expected"), [(2190, None), (2191, "medium"), (4380, "medium"), (4381, "high")]
)
def test_token_spike_boundaries(tokens: int, expected: str | None) -> None:
    draft = rules.token_spike(rule_input(execution(tokens_input=tokens)))
    assert (draft.severity if draft else None) == expected


def test_token_spike_needs_reported_tokens_on_both_sides() -> None:
    assert rules.token_spike(rule_input(execution())) is None  # this run reported no tokens
    no_token_history = Baseline(durations_ms=[100] * 20, token_totals=[10] * 4, step_counts=[1] * 20)
    assert rules.token_spike(rule_input(execution(tokens_input=10**6), baseline=no_token_history)) is None


# repeated_tool_failure


def test_repeated_tool_failure_within_one_execution() -> None:
    steps = [failed_tool_step(1), failed_tool_step(2, attempt=2), failed_tool_step(3, attempt=3)]
    draft = rules.repeated_tool_failure(rule_input(execution("failed"), steps))
    assert_well_formed(draft, "repeated_tool_failure", "high")
    assert draft.title == "Tool retrieve_kb failed 3 times in one execution"
    assert "Rule fires at 3 or more failed steps of the same tool in one execution." in draft.explanation
    assert [item["ref_id"] for item in draft.evidence] == [s.id for s in steps]
    assert draft.evidence[1]["label"] == "Step 2 retrieve_kb (attempt 2) failed"
    assert (draft.evidence[0]["observed"], draft.evidence[0]["excerpt"]) == ("429 Too Many Requests",) * 2


def test_repeated_tool_failure_needs_three_failures_of_the_same_tool() -> None:
    two = [failed_tool_step(1), failed_tool_step(2), step(3, "retrieve_kb", tool_name="retrieve_kb")]
    assert rules.repeated_tool_failure(rule_input(execution("failed"), two)) is None
    mixed = [failed_tool_step(1, "a"), failed_tool_step(2, "b"), failed_tool_step(3, "c")]
    assert rules.repeated_tool_failure(rule_input(execution("failed"), mixed)) is None
    not_a_tool = [step(index, "parse", "failed") for index in (1, 2, 3)]  # failed steps without a tool_name
    assert rules.repeated_tool_failure(rule_input(execution("failed"), not_a_tool)) is None


def test_repeated_tool_failure_across_the_last_three_executions() -> None:
    recent = [earlier(1, "failed", ("retrieve_kb", "other")), earlier(2, "completed", ("retrieve_kb",))]
    draft = rules.repeated_tool_failure(rule_input(execution("failed"), [failed_tool_step(1)], recent=recent))
    assert_well_formed(draft, "repeated_tool_failure", "high")
    assert draft.title == "Tool retrieve_kb failed in 3 executions in a row"
    assert [item["kind"] for item in draft.evidence] == ["step", "execution", "execution"]
    assert [item["ref_id"] for item in draft.evidence[1:]] == [recent[0].execution_id, recent[1].execution_id]


def test_repeated_tool_failure_across_executions_non_firing_cases() -> None:
    this = [failed_tool_step(1)]
    broken_streak = [
        earlier(1, "failed", ("retrieve_kb",)),
        earlier(2),
        earlier(3, "failed", ("retrieve_kb",)),
    ]
    assert rules.repeated_tool_failure(rule_input(execution("failed"), this, recent=broken_streak)) is None
    different_tools = [earlier(1, "failed", ("web_search",)), earlier(2, "failed", ("retrieve_kb",))]
    assert rules.repeated_tool_failure(rule_input(execution("failed"), this, recent=different_tools)) is None
    only_two = [earlier(1, "failed", ("retrieve_kb",))]
    assert rules.repeated_tool_failure(rule_input(execution("failed"), this, recent=only_two)) is None
    healthy_now = [earlier(1, "failed", ("retrieve_kb",)), earlier(2, "failed", ("retrieve_kb",))]
    assert rules.repeated_tool_failure(rule_input(execution(), [step(1)], recent=healthy_now)) is None


# excessive_retries


def test_excessive_retries_on_a_third_attempt() -> None:
    steps = [
        failed_tool_step(1),
        failed_tool_step(2, attempt=2),
        step(3, "retrieve_kb", tool_name="retrieve_kb", attempt=3),
    ]
    draft = rules.excessive_retries(rule_input(execution(), steps))
    assert_well_formed(draft, "excessive_retries", "medium")
    assert draft.title == "3 retries in one execution, up to attempt 3"
    assert draft.explanation == (
        "The highest attempt number in this execution is 3 and the sum of (attempt - 1) over all steps is 3. "
        "Rule fires when any step has attempt >= 3 or the sum is >= 5."
    )
    assert [(item["ref_id"], item["observed"]) for item in draft.evidence] == [
        (steps[2].id, 3),
        (steps[1].id, 2),
    ]


def test_excessive_retries_on_the_total() -> None:
    steps = [step(index, f"tool_{index}", attempt=2) for index in range(1, 6)]  # five second attempts
    draft = rules.excessive_retries(rule_input(execution(), steps))
    assert_well_formed(draft, "excessive_retries", "medium")
    assert draft.title == "5 retries in one execution, up to attempt 2"


def test_excessive_retries_non_firing_cases() -> None:
    assert rules.excessive_retries(rule_input(execution(), [step(1), step(2)])) is None
    four_second_attempts = [step(index, attempt=2) for index in range(1, 5)]  # sum 4, highest 2
    assert rules.excessive_retries(rule_input(execution(), four_second_attempts)) is None
    assert rules.excessive_retries(rule_input(execution())) is None


# repeated_timeouts


def test_repeated_timeouts_fires_at_three_of_the_last_ten() -> None:
    recent = [
        earlier(1),
        earlier(2, "timed_out"),
        earlier(3, "failed"),
        earlier(4, "timed_out"),
        *map(earlier, range(5, 10)),
    ]
    draft = rules.repeated_timeouts(rule_input(execution("timed_out"), recent=recent))
    assert_well_formed(draft, "repeated_timeouts", "high")
    assert draft.title == "3 of the last 10 executions timed out"
    assert "Rule fires at 3 or more timeouts in the agent's last 10 executions." in draft.explanation
    assert [item["ref_id"] for item in draft.evidence] == [
        EXECUTION_ID,
        recent[1].execution_id,
        recent[3].execution_id,
    ]
    assert draft.evidence[0]["label"] == "This execution timed out"


def test_repeated_timeouts_non_firing_cases() -> None:
    two = [earlier(1, "timed_out"), earlier(2)]
    assert rules.repeated_timeouts(rule_input(execution("timed_out"), recent=two)) is None
    outside_window = [*map(earlier, range(1, 10)), earlier(10, "timed_out"), earlier(11, "timed_out")]
    assert rules.repeated_timeouts(rule_input(execution("timed_out"), recent=outside_window)) is None
    # Three timeouts in the window, but this execution is healthy: it is not the one to flag.
    recovered = [earlier(1, "timed_out"), earlier(2, "timed_out"), earlier(3, "timed_out")]
    assert rules.repeated_timeouts(rule_input(execution("completed"), recent=recovered)) is None


# ghost_completion


def test_ghost_completion_when_an_expected_step_never_started() -> None:
    run = execution(config={"expected_steps": ["extract_fields", "validate", "submit_invoice"]})
    steps = [step(1, "extract_fields"), step(2, "validate")]
    draft = rules.ghost_completion(rule_input(run, steps))
    assert_well_formed(draft, "ghost_completion", "critical")
    assert draft.title == "Reported completed, but submit_invoice never completed"
    assert draft.explanation == (
        "The execution reported status completed, but expected 1 step never completed: submit_invoice. "
        "Rule fires when a completed execution has a step still running, an expected step "
        "(config.expected_steps) with no completed step, or no steps at all."
    )
    (item,) = draft.evidence
    assert (item["kind"], item["ref_id"], item["field"]) == (
        "execution",
        EXECUTION_ID,
        "config.expected_steps",
    )
    assert item["label"] == "Expected step submit_invoice never started"
    assert item["observed"] == ["extract_fields", "validate"]
    assert item["expected"] == ["extract_fields", "validate", "submit_invoice"]


def test_ghost_completion_when_an_expected_step_failed_or_is_still_running() -> None:
    run = execution(config={"expected_steps": ["validate", "submit_invoice"]})
    steps = [step(1, "validate", "failed"), step(2, "submit_invoice", "running")]
    draft = rules.ghost_completion(rule_input(run, steps))
    assert_well_formed(draft, "ghost_completion", "critical")
    assert "expected 2 steps never completed: validate, submit_invoice" in draft.explanation
    assert "1 step still running: submit_invoice" in draft.explanation
    assert [(item["kind"], item["ref_id"], item["observed"]) for item in draft.evidence] == [
        ("step", steps[0].id, "failed"),
        ("step", steps[1].id, "running"),
        ("step", steps[1].id, "running"),
    ]
    assert draft.evidence[0]["label"] == "Expected step validate never completed (last seen as failed)"


def test_ghost_completion_when_a_step_is_still_running() -> None:
    steps = [step(1, "plan"), step(2, "summarize", "running")]
    draft = rules.ghost_completion(rule_input(execution(), steps))
    assert_well_formed(draft, "ghost_completion", "critical")
    assert draft.title == "Reported completed while summarize was still running"
    assert draft.evidence[0]["label"] == "Step 2 summarize was still running when the execution completed"


def test_ghost_completion_when_no_steps_were_recorded() -> None:
    draft = rules.ghost_completion(rule_input(execution()))
    assert_well_formed(draft, "ghost_completion", "critical")
    assert draft.title == "Reported completed without recording any step"
    assert (draft.evidence[0]["field"], draft.evidence[0]["observed"]) == ("step_count", 0)


def test_ghost_completion_counts_a_retried_step_that_eventually_completed() -> None:
    run = execution(config={"expected_steps": ["retrieve_kb"]})
    steps = [failed_tool_step(1), step(2, "retrieve_kb", tool_name="retrieve_kb", attempt=2)]
    assert rules.ghost_completion(rule_input(run, steps)) is None


@pytest.mark.parametrize("status", ["failed", "timed_out", "running"])
def test_ghost_completion_only_applies_to_completed_executions(status: str) -> None:
    run = execution(status, config={"expected_steps": ["submit_invoice"]})
    assert rules.ghost_completion(rule_input(run, [step(1, "plan", "running")])) is None


def test_ghost_completion_does_not_fire_on_a_healthy_run() -> None:
    run = execution(
        config={"expected_steps": ["plan", "plan", "summarize"]}
    )  # a repeated name is one requirement
    assert (
        rules.ghost_completion(
            rule_input(run, [step(1, "plan"), step(2, "summarize"), step(3, "extra", "failed")])
        )
        is None
    )
    assert rules.ghost_completion(rule_input(execution(config={"expected_steps": None}), [step(1)])) is None
    assert rules.ghost_completion(rule_input(execution(config={"expected_steps": []}), [step(1)])) is None


def test_ghost_completion_title_stays_within_80_characters() -> None:
    name = "a_very_long_step_name_" * 5
    draft = rules.ghost_completion(rule_input(execution(config={"expected_steps": [name]}), [step(1)]))
    assert_well_formed(draft, "ghost_completion", "critical")
    assert draft.title == "Reported completed, but the recorded steps do not show it"


# stale_execution


def test_stale_execution_is_raised_only_by_the_sweeper() -> None:
    stale = StaleInfo(last_event_at=T0, timeout_ms=300000, idle_ms=312450)
    draft = rules.stale_execution(rule_input(execution("timed_out"), stale=stale))
    assert_well_formed(draft, "stale_execution", "high")
    assert draft.title == "No event for 312,450 ms; marked timed out"
    assert draft.explanation == (
        "The execution was running and sent no event for 312,450 ms (last event received at "
        "2026-11-14T10:00:00.000Z). Rule fires after config.timeout_ms = 300,000 ms without an event; "
        "Ghostwatch then marked the execution timed_out."
    )
    assert draft.evidence[0]["observed"] == {"last_event_at": "2026-11-14T10:00:00.000Z", "idle_ms": 312450}
    assert draft.evidence[0]["expected"] == {"timeout_ms": 300000}
    # An execution the client itself reported as timed out is not a stale execution.
    assert rules.stale_execution(rule_input(execution("timed_out"))) is None


# unexpected_pattern: baseline tools {web_search}; largest baseline step_count 5, so the limit is 10.


def test_unexpected_pattern_on_a_new_tool() -> None:
    steps = [
        step(1, "web_search", tool_name="web_search"),
        step(2, "send_email", tool_name="send_email"),
        step(3, "send_email", tool_name="send_email"),
    ]
    draft = rules.unexpected_pattern(rule_input(execution(), steps))
    assert_well_formed(draft, "unexpected_pattern", "low")
    assert draft.title == "New tool in this run: send_email"
    assert draft.explanation == (
        "Compared with the last 20 completed runs of research-assistant, it called 1 tool never seen in "
        "the baseline: send_email (baseline tools: web_search). Rule fires on a tool never seen in the "
        "baseline or on step_count above 2× the baseline maximum."
    )
    (item,) = draft.evidence
    assert (item["ref_id"], item["observed"], item["expected"]) == (steps[1].id, "send_email", ["web_search"])


def test_unexpected_pattern_on_step_count() -> None:
    many = [step(index, "web_search", tool_name="web_search") for index in range(1, 12)]  # 11 steps
    draft = rules.unexpected_pattern(rule_input(execution(), many))
    assert_well_formed(draft, "unexpected_pattern", "low")
    assert draft.title == "11 steps, baseline maximum is 5"
    assert "it recorded 11 steps, above 2× the largest baseline step count (5) = 10" in draft.explanation
    assert (draft.evidence[0]["observed"], draft.evidence[0]["expected"]) == (11, 10)
    assert rules.unexpected_pattern(rule_input(execution(), many[:10])) is None  # exactly 2x is not above


def test_unexpected_pattern_does_not_fire_on_a_familiar_run() -> None:
    steps = [
        step(1, "plan"),
        step(2, "web_search", tool_name="web_search"),
        step(3, "parse_results", "failed"),
    ]
    assert rules.unexpected_pattern(rule_input(execution("failed"), steps)) is None


def test_a_healthy_run_raises_nothing() -> None:
    run = execution(
        duration_ms=9800, tokens_input=900, tokens_output=200, config={"expected_steps": ["web_search"]}
    )
    steps = [step(1, "plan"), step(2, "web_search", tool_name="web_search"), step(3, "summarize")]
    recent = [earlier(index) for index in range(1, 10)]
    assert [
        rule.__name__ for rule in rules.RULES if rule(rule_input(run, steps, recent=recent)) is not None
    ] == []
    assert len(rules.RULES) == 8
