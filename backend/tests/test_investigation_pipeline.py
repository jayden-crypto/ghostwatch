"""Facts, signatures and verification: the deterministic parts of an investigation, without a database."""

from typing import Any

import pytest

from app.models import Anomaly, Execution, Step
from app.providers.llm.base import Proposal, ProviderError, ProviderResult
from app.providers.llm.rule_based import RuleBasedProvider
from app.schemas.investigations import InvestigationReport
from app.services.anomaly.baseline import Baseline
from app.services.investigation import signatures
from app.services.investigation.context import InvestigationContext
from app.services.investigation.engine import NO_ROOT_CAUSE, build_report
from app.services.investigation.facts import build_facts, find_failing_step, http_status_of
from app.services.investigation.prompts import PROPOSAL_SCHEMA, build_digest, build_user_message
from app.services.investigation.verify import verify
from tests.factories import T0

EXECUTION_ID = "exe_" + "e" * 32
KEY_ERROR = {"type": "KeyError", "message": "'results'", "stacktrace": "Traceback ...\nKeyError: 'results'"}
HTTP_429 = {"type": "RateLimited", "message": "HTTP 429 Too Many Requests", "stacktrace": None}
BASELINE = Baseline(
    durations_ms=[1000] * 20,
    token_totals=[500] * 20,
    step_counts=[4] * 20,
    tool_names=frozenset({"web_search"}),
)


def step(ordinal: int, name: str, status: str = "completed", **values: Any) -> Step:
    defaults = {"type": "custom", "attempt": 1, "started_at": T0, "metadata_": {}}
    return Step(
        id=f"stp_{ordinal:032x}",
        execution_id=EXECUTION_ID,
        ordinal=ordinal,
        name=name,
        status=status,
        **{**defaults, **values},
    )


def tool(ordinal: int, name: str, status: str = "completed", **values: Any) -> Step:
    return step(ordinal, name, status, type="tool_call", tool_name=name, **values)


def context(
    status: str,
    steps: list[Step],
    *,
    error: dict | None = None,
    config: dict | None = None,
    anomalies: list[Anomaly] | None = None,
    baseline: Baseline = BASELINE,
) -> InvestigationContext:
    execution = Execution(
        id=EXECUTION_ID, status=status, duration_ms=400, step_count=len(steps), error=error, config=config or {},
        started_at=T0,
    )  # fmt: skip
    return InvestigationContext(execution, steps, anomalies or [], baseline, "research-assistant")


def schema_change() -> InvestigationContext:
    """The demo failure: the search tool answers data/meta, and parse_results asks for 'results'."""
    steps = [
        step(1, "plan", type="reasoning", output={"query": "q"}),
        tool(2, "web_search", output={"data": [{"title": "t"}], "meta": {"total": 1}}),
        step(3, "parse_results", "failed", type="reasoning", error=KEY_ERROR),
    ]
    return context("failed", steps, error=KEY_ERROR)


def ghost_anomaly(step_id: str | None = None) -> Anomaly:
    evidence = [{"kind": "execution", "label": "Expected step submit_invoice never started", "ref_id": EXECUTION_ID,
                 "field": "config.expected_steps", "observed": ["validate"], "expected": ["validate", "submit_invoice"],
                 "excerpt": None}]  # fmt: skip
    if step_id:
        evidence.append({"kind": "step", "label": "still running", "ref_id": step_id, "field": "status",
                         "observed": "running", "expected": "completed", "excerpt": None})  # fmt: skip
    return Anomaly(
        id="anm_" + "a" * 32, type="ghost_completion", severity="critical", rule_id="ghost_completion.v1",
        title="Reported completed, but submit_invoice never completed", explanation="The execution reported ...",
        evidence=evidence,
    )  # fmt: skip


def fact_statements(ctx: InvestigationContext) -> dict[str, str]:
    facts = build_facts(ctx)
    by_id = {fact["id"]: fact["statement"] for fact in facts.facts}
    return {key: by_id[fact_id] for key, fact_id in facts.ids.items()}


# ---- facts ------------------------------------------------------------------------------------


def test_facts_of_the_schema_change_failure() -> None:
    ctx = schema_change()
    facts = build_facts(ctx)
    plan, search, parse = ctx.steps
    assert [fact["id"] for fact in facts.facts] == ["F1", "F2", "F3", "F4", "F5", "F6"]
    assert fact_statements(ctx) == {
        "outcome": "Execution of research-assistant ended with status failed after 400 ms and 3 steps.",
        "execution_error": "The execution ended with the error KeyError: 'results'.",
        "failing_step": "Step 3 parse_results failed with KeyError: 'results'.",
        f"output:{plan.id}": "Step 1 plan (reasoning, completed) returned an object with keys: query.",
        f"output:{search.id}": "Step 2 web_search (tool_call, completed) returned an object with keys: data, meta.",
        "baseline": (
            "This execution took 400 ms over 3 steps. Over the last 20 completed runs of research-assistant, "
            "the median duration is 1000 ms (p95 1000 ms) and the largest step count is 4."
        ),
    }
    assert facts.failing_step is parse and facts.gaps == []

    failing = facts.facts[2]["evidence"]
    assert [(item["kind"], item["ref_id"], item["field"]) for item in failing] == [
        ("step", parse.id, "error.message"),
        ("step", parse.id, "error.stacktrace"),
    ]
    assert (failing[0]["observed"], failing[0]["excerpt"]) == ("'results'", "'results'")
    assert failing[1]["excerpt"].endswith("KeyError: 'results'")
    output = facts.facts[4]["evidence"][0]
    assert (output["ref_id"], output["field"], output["observed"]) == (search.id, "output", ["data", "meta"])
    assert output["excerpt"] == '{"data":[{"title":"t"}],"meta":{"total":1}}'  # copied from the stored output
    assert all(len(fact["evidence"]) >= 1 for fact in facts.facts)


def test_failing_step_is_the_step_the_execution_error_escaped_from() -> None:
    inner_error = {"type": "ValueError", "message": "bad", "stacktrace": None}
    steps = [
        tool(1, "retrieve_kb", "failed", error=HTTP_429),  # an earlier failure the agent recovered from
        step(2, "outer", "failed", error=inner_error),
        step(3, "inner", "failed", error=inner_error, parent_step_id="stp_" + f"{2:032x}"),
        step(4, "cleanup", "failed", error={"type": "OSError", "message": "disk", "stacktrace": None}),
    ]
    assert find_failing_step(context("failed", steps, error=inner_error)).name == "inner"
    assert (
        find_failing_step(context("failed", steps, error={"type": "Other", "message": "x"})).name == "cleanup"
    )
    assert find_failing_step(context("failed", [step(1, "fine")], error=KEY_ERROR)) is None
    assert find_failing_step(context("completed", steps)) is None
    running = [step(1, "a"), step(2, "b", "running"), step(3, "c", "running")]
    assert find_failing_step(context("timed_out", running)).name == "c"


def test_facts_cover_retries_http_statuses_running_and_expected_steps() -> None:
    steps = [
        tool(1, "retrieve_kb", "failed", error=HTTP_429),
        tool(2, "retrieve_kb", "failed", attempt=2, error=HTTP_429),
        tool(3, "retrieve_kb", attempt=3, output={"articles": []}),
        tool(4, "fetch", output={"status": 503, "body": "upstream down"}),
        step(5, "draft_reply", "running"),
    ]
    ctx = context(
        "completed",
        steps,
        config={"expected_steps": ["retrieve_kb", "draft_reply"]},
        anomalies=[ghost_anomaly(steps[4].id)],
    )
    statements = fact_statements(ctx)
    assert statements["retry:retrieve_kb"] == (
        "retrieve_kb was attempted 3 times: attempt 1 failed (RateLimited), attempt 2 failed (RateLimited), "
        "attempt 3 completed."
    )
    assert (
        statements[f"http:{steps[0].id}"] == "Step 1 retrieve_kb (tool retrieve_kb) reported HTTP status 429."
    )
    assert statements[f"http:{steps[3].id}"] == "Step 4 fetch (tool fetch) reported HTTP status 503."
    assert (
        statements["running_steps"]
        == "1 step(s) were still running when the execution ended: Step 5 draft_reply."
    )
    assert statements["expected_steps"] == (
        "The execution is configured to expect these steps to complete: retrieve_kb, draft_reply. "
        "Steps that completed: retrieve_kb, fetch. Expected steps that did not complete: draft_reply."
    )
    assert statements["anomaly:ghost_completion"] == (
        "Anomaly ghost_completion (critical) was raised on this execution: "
        "Reported completed, but submit_invoice never completed."
    )
    anomaly_fact = next(f for f in build_facts(ctx).facts if f["statement"].startswith("Anomaly ghost"))
    assert [item["kind"] for item in anomaly_fact["evidence"]] == [
        "anomaly",
        "execution",
        "step",
    ]  # the anomaly's own evidence is carried over


def test_fact_gaps_name_what_is_missing() -> None:
    truncated = {"_truncated": True, "original_bytes": 103010, "preview": '{"rows":["xxx'}
    ctx = context(
        "failed",
        [tool(1, "export", output=truncated)],
        error=KEY_ERROR,
        baseline=Baseline(durations_ms=[1, 2]),
    )
    facts = build_facts(ctx)
    assert facts.gaps == [
        "Only 2 completed baseline run(s) exist for research-assistant; at least 5 are needed to compare this "
        "execution with normal behaviour.",
        "No step recorded the failure, so it happened outside any instrumented step.",
        "At least one step output was larger than 64 KB and is stored only as a preview.",
    ]
    assert "baseline" not in facts.ids
    statement = fact_statements(ctx)[f"output:{ctx.steps[0].id}"]
    assert "truncated at ingestion (103010 bytes; only a preview is stored)" in statement


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"output": {"status": 404}}, 404),
        ({"output": {"status_code": 500, "ok": False}}, 500),
        ({"output": {"status": 200}}, None),
        ({"output": {"status": "error"}}, None),
        ({"output": {"status": True}}, None),
        ({"error": {"type": "HTTPError", "message": "HTTP 503: unavailable"}}, 503),
        ({"error": {"type": "RateLimited", "message": "HTTP 429 Too Many Requests"}}, 429),
        ({"error": {"type": "ValueError", "message": "expected 500 rows, got 3"}}, None),
        ({"error": {"type": "HTTPError", "message": "429 Too Many Requests"}}, 429),
        ({"error": {"type": "RequestFailed", "message": "upstream answered with status code: 404"}}, 404),
        ({"error": {"type": "TimeoutError", "message": "HTTP timeout after 500 ms"}}, None),
        ({"error": {"type": "ValueError", "message": "status 200 but 503 rows missing"}}, None),
        ({"output": [404]}, None),
    ],
)
def test_http_status_detection(values: dict, expected: int | None) -> None:
    assert http_status_of(tool(1, "fetch", **values)) == expected
    assert http_status_of(step(1, "not_a_tool", **values)) is None


# ---- signatures: one matching and one non-matching case each -----------------------------------


def matched(ctx: InvestigationContext) -> list[str]:
    return [match.signature for match in signatures.match_signatures(ctx, build_facts(ctx))]


def test_missing_key_in_upstream_output_matches_the_schema_change() -> None:
    ctx = schema_change()
    facts = build_facts(ctx)
    match = signatures.missing_key_in_upstream_output(ctx, facts)
    assert match.signature == "missing_key_in_upstream_output"
    assert match.statement == (
        "Step 3 parse_results read the key 'results', which the output of Step 2 web_search (tool web_search) "
        "does not contain. That output's keys are: data, meta."
    )
    assert match.supporting_fact_ids == ["F3", "F5"]  # the failing step and the tool output
    assert match.step_ids == [ctx.steps[1].id, ctx.steps[2].id]
    assert "data, meta" in match.action
    assert matched(ctx) == ["missing_key_in_upstream_output"]


@pytest.mark.parametrize(
    "steps",
    [
        # the key is present upstream, so the KeyError came from somewhere else
        [
            tool(1, "web_search", output={"results": [], "total": 0}),
            step(2, "parse_results", "failed", error=KEY_ERROR),
        ],
        # not a KeyError
        [
            tool(1, "web_search", output={"data": []}),
            step(
                2,
                "parse_results",
                "failed",
                error={"type": "TypeError", "message": "'results'", "stacktrace": None},
            ),
        ],
        # no tool output before the failing step
        [step(1, "plan", output={"data": []}), step(2, "parse_results", "failed", error=KEY_ERROR)],
        # the upstream output was truncated: absence of the key cannot be proven
        [
            tool(1, "web_search", output={"_truncated": True, "original_bytes": 99999, "preview": "{"}),
            step(2, "parse_results", "failed", error=KEY_ERROR),
        ],
        # the tool returned a list, not an object
        [tool(1, "web_search", output=[1, 2]), step(2, "parse_results", "failed", error=KEY_ERROR)],
        # the KeyError message is not a key literal
        [
            tool(1, "web_search", output={"data": []}),
            step(
                2,
                "parse_results",
                "failed",
                error={"type": "KeyError", "message": "no such thing", "stacktrace": None},
            ),
        ],
        # the only tool call before it failed
        [
            tool(1, "web_search", "failed", error=HTTP_429, output={"data": []}),
            step(2, "parse_results", "failed", error=KEY_ERROR),
        ],
    ],
    ids=[
        "key-present",
        "not-keyerror",
        "no-tool",
        "truncated",
        "list-output",
        "unparseable-key",
        "tool-failed",
    ],
)
def test_missing_key_in_upstream_output_does_not_match(steps: list[Step]) -> None:
    ctx = context("failed", steps, error=steps[-1].error)
    assert signatures.missing_key_in_upstream_output(ctx, build_facts(ctx)) is None


def test_missing_key_handles_integer_keys_and_uses_the_nearest_tool() -> None:
    error = {"type": "KeyError", "message": "3", "stacktrace": None}
    steps = [
        tool(1, "old", output={"a": 1}),
        tool(2, "lookup", output={"1": "x"}),
        step(3, "a"),
        step(4, "b"),
        step(5, "c"),
        step(6, "pick", "failed", error=error),
    ]
    ctx = context("failed", steps, error=error)
    match = signatures.missing_key_in_upstream_output(ctx, build_facts(ctx))
    assert "read the key 3" in match.statement and "Step 2 lookup" in match.statement
    assert len(match.supporting_fact_ids) == 2  # the tool output is a fact even though it is 4 steps back


def test_retry_exhaustion() -> None:
    steps = [
        tool(1, "retrieve_kb", "failed", error=HTTP_429),
        tool(2, "retrieve_kb", "failed", attempt=2, error=HTTP_429),
        tool(3, "retrieve_kb", "failed", attempt=3, error=HTTP_429),
    ]
    ctx = context("failed", steps, error=HTTP_429)
    match = signatures.retry_exhaustion(ctx, build_facts(ctx))
    assert match.statement == (
        "retrieve_kb failed on all 3 attempts; the last one (Step 3 retrieve_kb (attempt 3)) failed with "
        "RateLimited: HTTP 429 Too Many Requests, and the execution failed."
    )
    assert match.step_ids == [s.id for s in steps]
    assert matched(ctx) == [
        "retry_exhaustion",
        "tool_http_error",
    ]  # both hold; retry exhaustion is the root cause

    recovered = [
        *steps[:2],
        tool(3, "retrieve_kb", attempt=3, output={"articles": []}),
        step(4, "draft", "failed", error=KEY_ERROR),
    ]
    ctx = context("failed", recovered, error=KEY_ERROR)
    assert signatures.retry_exhaustion(ctx, build_facts(ctx)) is None  # the last attempt succeeded
    single = [tool(1, "retrieve_kb", "failed", error=HTTP_429)]
    ctx = context("failed", single, error=HTTP_429)
    assert signatures.retry_exhaustion(ctx, build_facts(ctx)) is None  # never retried


def test_tool_http_error() -> None:
    type_error = {"type": "TypeError", "message": "NoneType", "stacktrace": None}
    steps = [
        tool(1, "fetch", output={"status": 502, "body": None}),
        step(2, "parse", "failed", error=type_error),
    ]
    ctx = context("failed", steps, error=type_error)
    match = signatures.tool_http_error(ctx, build_facts(ctx))
    assert match.statement == (
        "Step 1 fetch (tool fetch) reported HTTP status 502, and the later Step 2 parse then failed with "
        "TypeError: NoneType."
    )
    assert matched(ctx) == ["tool_http_error"]

    itself = context("failed", [tool(1, "fetch", "failed", error=HTTP_429)], error=HTTP_429)
    assert (
        signatures.tool_http_error(itself, build_facts(itself)).statement
        == "Step 1 fetch (tool fetch) failed with HTTP status 429."
    )

    # A run that hit 429s but recovered and completed is not a tool_http_error failure.
    recovered = context(
        "completed",
        [tool(1, "fetch", "failed", error=HTTP_429), tool(2, "fetch", attempt=2, output={"status": 200})],
    )
    assert signatures.tool_http_error(recovered, build_facts(recovered)) is None
    # A 429 the agent retried past is not the cause of a later, unrelated failure.
    retried = [
        tool(1, "fetch", "failed", error=HTTP_429),
        tool(2, "fetch", attempt=2, output={"status": 200}),
        step(3, "parse", "failed", error=type_error),
    ]
    unrelated = context("failed", retried, error=type_error)
    assert signatures.tool_http_error(unrelated, build_facts(unrelated)) is None
    assert matched(unrelated) == []
    after = context(
        "failed",
        [step(1, "parse", "failed", error=type_error), tool(2, "fetch", output={"status": 502})],
        error=type_error,
    )
    assert (
        signatures.tool_http_error(after, build_facts(after)) is None
    )  # the HTTP error came after the failure


def test_timeout_in_step() -> None:
    ctx = context("timed_out", [step(1, "plan"), tool(2, "web_search", "running")])
    match = signatures.timeout_in_step(ctx, build_facts(ctx))
    assert (
        match.statement
        == "The execution timed out while Step 2 web_search was running; that step never finished."
    )
    assert matched(ctx) == ["timeout_in_step"]

    idle = context("timed_out", [step(1, "plan")])
    assert signatures.timeout_in_step(idle, build_facts(idle)) is None  # nothing was running
    failed = context("failed", [step(1, "plan", "running")], error=KEY_ERROR)
    assert signatures.timeout_in_step(failed, build_facts(failed)) is None  # not a timeout


def test_ghost_completion_signature() -> None:
    steps = [step(1, "validate"), step(2, "notify", "running")]
    ctx = context(
        "completed",
        steps,
        config={"expected_steps": ["validate", "submit_invoice"]},
        anomalies=[ghost_anomaly(steps[1].id)],
    )
    facts = build_facts(ctx)
    match = signatures.ghost_completion(ctx, facts)
    assert match.statement == (
        "The agent reported the run as completed, but the recorded steps contradict it: "
        "Reported completed, but submit_invoice never completed."
    )
    assert match.supporting_fact_ids == facts.cite(
        "anomaly:ghost_completion", "expected_steps", "running_steps"
    )
    assert len(match.supporting_fact_ids) == 3 and match.step_ids == [steps[1].id]

    healthy = context("completed", [step(1, "validate")], config={"expected_steps": ["validate"]})
    assert signatures.ghost_completion(healthy, build_facts(healthy)) is None
    assert matched(healthy) == []


# ---- verification: the honesty rules -----------------------------------------------------------


def hypothesis(**values: Any) -> dict[str, Any]:
    return {"statement": "The search API changed.", "confidence": "medium", "reasoning": "F1 shows it.",
            "supporting_fact_ids": ["F1"], "contradicting_fact_ids": [], "relevant_step_ids": [], **values}  # fmt: skip


def check(proposal: dict[str, Any], first_number: int = 1):
    return verify(
        Proposal.model_validate(proposal), fact_ids={"F1", "F2", "F3"}, step_ids={"stp_a", "stp_b"},
        source="test-model", first_number=first_number,
    )  # fmt: skip


def test_verify_keeps_what_the_evidence_supports() -> None:
    result = check(
        {
            "hypotheses": [
                hypothesis(
                    supporting_fact_ids=["F1", "F3", "F1"],
                    contradicting_fact_ids=["F2"],
                    relevant_step_ids=["stp_a"],
                )
            ],
            "recommendations": [
                {"action": "Pin the API version.", "rationale": "Stops drift.", "hypothesis_index": 0},
                {"action": "Add an alert.", "rationale": "Catch it sooner."},
            ],
            "root_cause": {"hypothesis_index": 0, "status": "probable"},
            "evidence_gaps": ["The search API's response headers were not recorded.", "  "],
        },
        first_number=2,
    )
    assert result.hypotheses == [
        {"id": "H2", "statement": "The search API changed.", "confidence": "medium", "reasoning": "F1 shows it.",
         "supporting_fact_ids": ["F1", "F3"], "contradicting_fact_ids": ["F2"]}
    ]  # fmt: skip
    assert result.recommendations == [
        {"action": "Pin the API version.", "rationale": "Stops drift.", "hypothesis_id": "H2"},
        {"action": "Add an alert.", "rationale": "Catch it sooner.", "hypothesis_id": None},
    ]
    assert (result.root_hypothesis_id, result.step_ids) == ("H2", ["stp_a"])
    assert result.gaps == ["The search API's response headers were not recorded."]


def test_verify_drops_hypotheses_with_bad_citations() -> None:
    result = check(
        {
            "hypotheses": [
                hypothesis(statement="cites a fact that does not exist", supporting_fact_ids=["F1", "F9"]),
                hypothesis(statement="cites a step that is not in the trace", relevant_step_ids=["stp_zzz"]),
                hypothesis(statement="contradicting fact does not exist", contradicting_fact_ids=["F0"]),
                hypothesis(statement="cites nothing", supporting_fact_ids=[]),
                hypothesis(statement="   "),
                hypothesis(statement="the only supported one"),
            ],
            "recommendations": [
                {"action": "from a dropped hypothesis", "rationale": "x", "hypothesis_index": 0},
                {"action": "from the kept one", "rationale": "y", "hypothesis_index": 5},
                {"action": "index out of range", "rationale": "z", "hypothesis_index": 17},
            ],
            "root_cause": {"hypothesis_index": 0, "status": "probable"},
        }
    )
    assert [(h["id"], h["statement"]) for h in result.hypotheses] == [("H1", "the only supported one")]
    assert [r["action"] for r in result.recommendations] == ["from the kept one"]
    assert (
        result.root_hypothesis_id == "H1"
    )  # the claimed root cause was dropped, so the surviving one stands
    assert result.gaps == [
        "A hypothesis proposed by test-model was discarded because it cited fact id(s) that do not exist (F9).",
        "A hypothesis proposed by test-model was discarded because it cited step id(s) that are not in the trace (stp_zzz).",
        "A hypothesis proposed by test-model was discarded because it cited fact id(s) that do not exist (F0).",
        "A hypothesis proposed by test-model was discarded because it cited no supporting fact.",
        "A hypothesis proposed by test-model was discarded because it had no statement.",
    ]


def test_verify_never_lets_a_provider_confirm() -> None:
    result = check(
        {
            "hypotheses": [hypothesis(confidence="high")],
            "root_cause": {"hypothesis_index": 0, "status": "confirmed"},
        }
    )
    assert result.root_hypothesis_id == "H1"  # kept, but only ever as a hypothesis
    assert result.gaps == [
        "test-model labelled its root cause as confirmed. Only a deterministic signature can confirm a root "
        "cause, so it is reported as a hypothesis."
    ]


def test_verify_with_no_surviving_hypothesis_has_no_root_cause() -> None:
    nothing = check(
        {
            "hypotheses": [hypothesis(supporting_fact_ids=["F7"])],
            "root_cause": {"hypothesis_index": 0, "status": "confirmed"},
        }
    )
    assert (nothing.hypotheses, nothing.root_hypothesis_id) == ([], None)
    unsure = check(
        {
            "hypotheses": [hypothesis()],
            "root_cause": {"hypothesis_index": None, "status": "insufficient_evidence"},
        }
    )
    assert (
        len(unsure.hypotheses) == 1 and unsure.root_hypothesis_id is None
    )  # the model's own doubt is respected
    assert check({}).hypotheses == []


# ---- report assembly ---------------------------------------------------------------------------


class StubProvider:
    """A provider that returns whatever the test gives it, or raises."""

    name = "fable"

    def __init__(self, proposal: dict[str, Any] | None = None, error: str | None = None) -> None:
        self.proposal, self.error, self.calls = proposal, error, []

    def investigate(self, facts: list, digest: dict, confirmed: list) -> ProviderResult:
        self.calls.append((facts, digest, confirmed))
        if self.error:
            raise ProviderError(self.error)
        return ProviderResult(
            proposal=Proposal.model_validate(self.proposal), model="stub-model-1", raw={"id": "msg_1"}
        )


def test_rule_based_report_confirms_the_schema_change() -> None:
    ctx = schema_change()
    report, provider, model, raw = build_report(ctx, RuleBasedProvider())
    assert isinstance(report, InvestigationReport)
    assert (provider, model, raw) == ("rule_based", None, None)
    assert report.summary == (
        "The execution failed at Step 3 parse_results with KeyError: 'results'. "
        "The root cause is confirmed by the deterministic signature missing_key_in_upstream_output."
    )
    assert (report.root_cause.status, report.root_cause.signature, report.root_cause.hypothesis_id) == (
        "confirmed", "missing_key_in_upstream_output", "H1",
    )  # fmt: skip
    assert report.failing_step_id == ctx.steps[2].id
    assert report.relevant_step_ids == [ctx.steps[1].id, ctx.steps[2].id]
    (hypothesis_,) = report.hypotheses
    assert (hypothesis_.id, hypothesis_.confidence, hypothesis_.supporting_fact_ids) == (
        "H1",
        "high",
        ["F3", "F5"],
    )
    assert hypothesis_.statement == report.root_cause.statement
    (recommendation,) = report.recommendations
    assert (recommendation.id, recommendation.hypothesis_id) == ("R1", "H1")
    assert report.evidence_gaps == []


def test_rule_based_report_without_a_signature_says_insufficient_evidence() -> None:
    error = {"type": "ZeroDivisionError", "message": "division by zero", "stacktrace": None}
    ctx = context("failed", [step(1, "plan"), step(2, "score", "failed", error=error)], error=error)
    report, provider, _, _ = build_report(ctx, RuleBasedProvider())
    assert provider == "rule_based"
    assert (report.root_cause.status, report.root_cause.statement) == ("insufficient_evidence", NO_ROOT_CAUSE)
    assert (report.root_cause.hypothesis_id, report.root_cause.signature) == (None, None)
    assert (report.hypotheses, report.recommendations) == ([], [])
    assert len(report.facts) >= 3 and report.failing_step_id == ctx.steps[1].id
    assert report.summary.endswith("The recorded evidence is not sufficient to determine a root cause.")


def test_llm_hypotheses_are_added_but_cannot_override_a_signature() -> None:
    ctx = schema_change()
    proposal = {
        "hypotheses": [
            hypothesis(
                statement="The search provider shipped a v2 response format.",
                supporting_fact_ids=["F5"],
                relevant_step_ids=[ctx.steps[1].id],
            ),
            hypothesis(statement="Made up.", supporting_fact_ids=["F42"]),
        ],
        "recommendations": [
            {
                "action": "Add a contract test for the search API.",
                "rationale": "Catches drift.",
                "hypothesis_index": 0,
            }
        ],
        "root_cause": {"hypothesis_index": 0, "status": "confirmed"},
        "evidence_gaps": ["The search API's version header was not recorded."],
    }
    stub = StubProvider(proposal)
    report, provider, model, raw = build_report(ctx, stub)
    assert (provider, model, raw) == ("fable", "stub-model-1", {"id": "msg_1"})
    # The root cause is still the signature's; the model's "confirmed" changed nothing.
    assert (report.root_cause.status, report.root_cause.hypothesis_id) == ("confirmed", "H1")
    assert [(h.id, h.statement) for h in report.hypotheses] == [
        ("H1", report.root_cause.statement),
        ("H2", "The search provider shipped a v2 response format."),
    ]
    assert [(r.id, r.hypothesis_id) for r in report.recommendations] == [("R1", "H1"), ("R2", "H2")]
    assert report.evidence_gaps == [
        "A hypothesis proposed by stub-model-1 was discarded because it cited fact id(s) that do not exist (F42).",
        "stub-model-1 labelled its root cause as confirmed. Only a deterministic signature can confirm a root "
        "cause, so it is reported as a hypothesis.",
        "The search API's version header was not recorded.",
    ]
    # What the model was shown: the facts, a digest, and the cause the signature already confirmed.
    facts, digest, confirmed = stub.calls[0]
    assert [fact["id"] for fact in facts] == ["F1", "F2", "F3", "F4", "F5", "F6"]
    assert confirmed == [
        {"signature": "missing_key_in_upstream_output", "statement": report.root_cause.statement}
    ]
    assert [s["step_id"] for s in digest["steps"]] == [s.id for s in ctx.steps]


def test_llm_root_cause_is_only_ever_probable() -> None:
    error = {"type": "ZeroDivisionError", "message": "division by zero", "stacktrace": None}
    ctx = context(
        "failed",
        [step(1, "plan", output={"weights": []}), step(2, "score", "failed", error=error)],
        error=error,
    )
    proposal = {"hypotheses": [hypothesis(statement="The weights list was empty.", supporting_fact_ids=["F3", "F4"], confidence="high")],
                "root_cause": {"hypothesis_index": 0, "status": "confirmed"}}  # fmt: skip
    report, provider, _, _ = build_report(ctx, StubProvider(proposal))
    assert provider == "fable"
    assert (report.root_cause.status, report.root_cause.hypothesis_id, report.root_cause.signature) == (
        "probable",
        "H1",
        None,
    )
    assert report.root_cause.statement == "The weights list was empty."
    assert "The root cause given is a hypothesis; it is not confirmed." in report.summary

    all_dropped = {
        "hypotheses": [hypothesis(supporting_fact_ids=["F99"])],
        "root_cause": {"hypothesis_index": 0, "status": "confirmed"},
    }
    report, _, _, _ = build_report(ctx, StubProvider(all_dropped))
    assert report.root_cause.status == "insufficient_evidence" and report.hypotheses == []


@pytest.mark.parametrize(
    "reason", ["timed out after 60 s", "was rate limited", "returned output that did not match the schema"]
)
def test_a_failing_provider_falls_back_to_deterministic_findings_and_says_so(reason: str) -> None:
    report, provider, model, raw = build_report(schema_change(), StubProvider(error=reason))
    assert (provider, model, raw) == (
        "rule_based",
        None,
        None,
    )  # reported truthfully: the LLM contributed nothing
    assert report.root_cause.status == "confirmed" and len(report.hypotheses) == 1
    assert report.evidence_gaps == [
        f"No LLM hypotheses: the fable provider {reason}. This report contains deterministic findings only."
    ]


def test_an_unconfigured_provider_is_reported() -> None:
    report, provider, _, _ = build_report(
        schema_change(), RuleBasedProvider(), "LLM_PROVIDER is fable but no ANTHROPIC_API_KEY is configured"
    )
    assert provider == "rule_based"
    assert report.evidence_gaps == [
        "No LLM hypotheses: LLM_PROVIDER is fable but no ANTHROPIC_API_KEY is configured. "
        "This report contains deterministic findings only."
    ]


# ---- what the model is shown -------------------------------------------------------------------


def test_digest_is_compact_and_the_prompt_carries_ids() -> None:
    big = {"rows": ["x" * 100] * 1000}
    steps = [tool(index, "export", output=big, input={"page": index}) for index in range(1, 81)]
    ctx = context(
        "failed",
        [*steps, step(81, "parse", "failed", error=KEY_ERROR, parent_step_id=steps[-1].id)],
        error=KEY_ERROR,
    )
    digest = build_digest(ctx)
    assert digest["steps_omitted_from_the_middle"] == 21 and len(digest["steps"]) == 60
    assert [s["ordinal"] for s in digest["steps"][:2]] == [1, 2] and digest["steps"][-1]["ordinal"] == 81
    assert digest["steps"][-1]["parent_ordinal"] == 80
    assert all(len(s["output"] or "") <= 301 for s in digest["steps"])  # never the raw 100 KB payloads
    assert digest["execution"]["error"] == {"type": "KeyError", "message": "'results'"}

    facts = build_facts(ctx)
    message = build_user_message(facts.facts, digest, [])
    assert len(message) < 60_000
    assert message.index("<FACTS>") < message.index("<TRACE>") < message.index("<CONFIRMED>")
    assert '"id": "F1"' in message and steps[0].id in message
    assert "stacktrace" not in str(digest)  # the digest carries each error's type and message only


def test_proposal_schema_matches_the_proposal_model_and_structured_output_rules() -> None:
    def objects(node: Any):
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for value in node.values():
                yield from objects(value)
        elif isinstance(node, list):
            for value in node:
                yield from objects(value)

    for schema in objects(PROPOSAL_SCHEMA):
        assert schema["additionalProperties"] is False
        assert sorted(schema["required"]) == sorted(schema["properties"])
    assert set(PROPOSAL_SCHEMA["properties"]) == set(Proposal.model_fields)
    assert PROPOSAL_SCHEMA["properties"]["root_cause"]["properties"]["status"]["enum"] == [
        "probable",
        "insufficient_evidence",
    ]
    unsupported = {"minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "pattern"}
    assert not unsupported & set(str(PROPOSAL_SCHEMA).replace("'", " ").split())
