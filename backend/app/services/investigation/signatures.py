"""Deterministic failure signatures. Only a match here can mark a root cause `confirmed`.

Each signature is a small pure function over the stored trace: it either recognises one specific,
checkable failure pattern or returns None. A match names the facts that satisfy it.
"""

import ast
from collections.abc import Callable
from dataclasses import dataclass

from app.models import Step
from app.services.investigation.context import InvestigationContext
from app.services.investigation.facts import FactSet, error_text, step_label


@dataclass(frozen=True)
class SignatureMatch:
    signature: str
    statement: str  # the root cause, in words
    reasoning: str  # the condition the signature checks and how the facts satisfy it
    supporting_fact_ids: list[str]
    step_ids: list[str]
    action: str  # recommended next action
    rationale: str


def _missing_key(message: str) -> str | int | None:
    """The key a KeyError names. Python renders it as repr(key): "'results'" or 3."""
    try:
        key = ast.literal_eval(message)
    except (ValueError, SyntaxError):
        return None
    return key if isinstance(key, str | int) and not isinstance(key, bool) else None


def _nearest_tool_output_before(context: InvestigationContext, step: Step) -> Step | None:
    earlier = [
        s for s in context.steps if s.ordinal < step.ordinal and s.tool_name and s.status == "completed"
    ]
    return earlier[-1] if earlier else None


def missing_key_in_upstream_output(context: InvestigationContext, facts: FactSet) -> SignatureMatch | None:
    """The failing step raised KeyError(k), and the nearest preceding tool output has no key k."""
    step = facts.failing_step
    if step is None or step.status != "failed" or step.error.get("type") != "KeyError":
        return None
    key = _missing_key(step.error.get("message", ""))
    upstream = _nearest_tool_output_before(context, step)
    if key is None or upstream is None or not isinstance(upstream.output, dict):
        return None
    if upstream.output.get("_truncated") is True or key in upstream.output:
        return None  # a truncated output cannot prove the key is absent
    keys = ", ".join(sorted(upstream.output)) or "(none)"
    return SignatureMatch(
        signature="missing_key_in_upstream_output",
        statement=(
            f"{step_label(step)} read the key {key!r}, which the output of {step_label(upstream)} "
            f"(tool {upstream.tool_name}) does not contain. That output's keys are: {keys}."
        ),
        reasoning=(
            f"Signature missing_key_in_upstream_output: the failing step raised KeyError for {key!r} and the "
            f"nearest preceding tool output has no key {key!r}. Both conditions are read directly from the "
            "recorded step error and the recorded tool output."
        ),
        supporting_fact_ids=facts.cite("failing_step", f"output:{upstream.id}"),
        step_ids=[upstream.id, step.id],
        action=(
            f"Make {step.name} handle the response shape {upstream.tool_name} now returns (keys: {keys}), "
            f"or pin the response format of {upstream.tool_name}."
        ),
        rationale=f"{step.name} indexes the key {key!r} directly, and the tool's output no longer has it.",
    )


def retry_exhaustion(context: InvestigationContext, facts: FactSet) -> SignatureMatch | None:
    """The final attempt of a retried step failed, and the execution failed."""
    step = facts.failing_step
    if step is None or step.status != "failed" or step.attempt < 2 or context.execution.status != "failed":
        return None
    attempts = [s for s in context.steps if s.name == step.name]
    if attempts[-1] is not step or any(s.status == "completed" for s in attempts):
        return None
    return SignatureMatch(
        signature="retry_exhaustion",
        statement=(
            f"{step.name} failed on all {len(attempts)} attempts; the last one ({step_label(step)}) failed "
            f"with {error_text(step.error)}, and the execution failed."
        ),
        reasoning=(
            f"Signature retry_exhaustion: the step was retried, no attempt completed, and the final attempt "
            f"(attempt {step.attempt}) failed. The attempt history is read from the recorded steps."
        ),
        supporting_fact_ids=facts.cite(f"retry:{step.name}", "failing_step"),
        step_ids=[s.id for s in attempts],
        action=(
            f"Find out why {step.name} keeps failing before raising its retry budget; "
            "add backoff between attempts."
        ),
        rationale=f"Every one of the {len(attempts)} attempts failed, so retrying alone did not help.",
    )


def tool_http_error(context: InvestigationContext, facts: FactSet) -> SignatureMatch | None:
    """The last tool call up to the failing step reported an HTTP status >= 400, and the execution failed.

    Only the most recent tool call counts: an HTTP error that a later attempt recovered from is not
    what a subsequent, unrelated failure should be blamed on.
    """
    failing = facts.failing_step
    if failing is None or failing.status != "failed" or context.execution.status != "failed":
        return None
    tool_steps = [s for s in context.steps if s.tool_name and s.ordinal <= failing.ordinal]
    if not tool_steps or tool_steps[-1].id not in facts.http_statuses:
        return None
    tool_step = tool_steps[-1]
    status = facts.http_statuses[tool_step.id]
    if tool_step is failing:
        statement = f"{step_label(tool_step)} (tool {tool_step.tool_name}) failed with HTTP status {status}."
    else:
        statement = (
            f"{step_label(tool_step)} (tool {tool_step.tool_name}) reported HTTP status {status}, and the "
            f"later {step_label(failing)} then failed with {error_text(failing.error)}."
        )
    return SignatureMatch(
        signature="tool_http_error",
        statement=statement,
        reasoning=(
            "Signature tool_http_error: the last tool call up to the failing step recorded an HTTP status of "
            "400 or above in its output or error, and that step or a step after it failed the execution."
        ),
        supporting_fact_ids=facts.cite(f"http:{tool_step.id}", "failing_step"),
        step_ids=list(dict.fromkeys([tool_step.id, failing.id])),
        action=(
            f"Handle HTTP {status} from {tool_step.tool_name} explicitly: retry with backoff if it is "
            "transient, "
            "otherwise stop with a clear error before later steps run on a bad response."
        ),
        rationale=f"The run continued or failed on an HTTP {status} response from {tool_step.tool_name}.",
    )


def timeout_in_step(context: InvestigationContext, facts: FactSet) -> SignatureMatch | None:
    """The execution timed out while a step was still running."""
    step = facts.failing_step
    if context.execution.status != "timed_out" or step is None or step.status != "running":
        return None
    return SignatureMatch(
        signature="timeout_in_step",
        statement=f"The execution timed out while {step_label(step)} was running; that step never finished.",
        reasoning=(
            "Signature timeout_in_step: the execution's status is timed_out and a step that had started "
            "has no completion or failure event."
        ),
        supporting_fact_ids=facts.cite("failing_step", "anomaly:stale_execution"),
        step_ids=[step.id],
        action=f"Put a timeout around {step.name} and have it fail with an error instead of hanging.",
        rationale=f"{step.name} is where the run stopped making progress.",
    )


def ghost_completion(context: InvestigationContext, facts: FactSet) -> SignatureMatch | None:
    """The ghost_completion anomaly was raised: the agent reported success the recorded steps contradict."""
    anomaly = next((a for a in context.anomalies if a.type == "ghost_completion"), None)
    if anomaly is None:
        return None
    step_ids = [item["ref_id"] for item in anomaly.evidence if item["kind"] == "step" and item["ref_id"]]
    return SignatureMatch(
        signature="ghost_completion",
        statement=(
            f"The agent reported the run as completed, but the recorded steps contradict it: {anomaly.title}."
        ),
        reasoning=(
            "Signature ghost_completion: the execution's status is completed and the deterministic "
            "ghost_completion rule fired (a step still running, an expected step with no completed step, "
            "or no steps at all)."
        ),
        supporting_fact_ids=facts.cite("anomaly:ghost_completion", "expected_steps", "running_steps"),
        step_ids=list(dict.fromkeys(step_ids)),
        action=(
            "Make the agent fail the run when a required step does not complete, instead of reporting "
            "success; "
            "check for errors that are caught and ignored before the missing step."
        ),
        rationale=(
            "The run's reported outcome and its recorded steps disagree, so the reported outcome is not "
            "trustworthy."
        ),
    )


# Order matters: the first match is the root cause, later matches are listed as further hypotheses.
SIGNATURES: tuple[Callable[[InvestigationContext, FactSet], SignatureMatch | None], ...] = (
    missing_key_in_upstream_output,
    retry_exhaustion,
    tool_http_error,
    timeout_in_step,
    ghost_completion,
)


def match_signatures(context: InvestigationContext, facts: FactSet) -> list[SignatureMatch]:
    return [match for signature in SIGNATURES if (match := signature(context, facts)) is not None]
