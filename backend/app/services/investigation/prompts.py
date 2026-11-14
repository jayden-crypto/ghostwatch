"""What the model is shown and asked: the system prompt, the trace digest and the output schema.

Kept in one file so the prompt can be reviewed as a whole. The model sees facts (with ids), a
compact digest of the trace and any root cause the signatures already confirmed. It never sees raw
64 KB payloads, and nothing it returns is trusted until `verify.py` has checked it.
"""

import json
from typing import Any

from app.services.evidence import json_excerpt
from app.services.investigation.context import InvestigationContext

DIGEST_VALUE_CHARS = 300
DIGEST_MAX_STEPS = 60  # the first 20 and the last 40 steps of longer runs

SYSTEM_PROMPT = """\
You are an experienced site reliability engineer analysing one run of an AI agent for Ghostwatch, an \
observability tool for agents. Ghostwatch's promise to its users is that every claim in an investigation \
can be traced back to recorded evidence, so your analysis is only useful if it stays inside that evidence.

You are given three things:
- FACTS: statements that Ghostwatch's code derived from the recorded events, each with an id (F1, F2, ...). \
They are established. You do not need to re-derive or restate them.
- TRACE: a compact digest of the run's steps (ids, names, status, errors, shortened inputs and outputs).
- CONFIRMED: root causes that deterministic signature checks have already established, if any.

Propose hypotheses about why the run failed or behaved abnormally, and recommend what the developer \
should do next.

The backend checks your answer after you respond, and discards whatever breaks these rules:
- Cite facts only by the ids in FACTS, and steps only by the step ids in TRACE. A hypothesis that cites \
an id that does not exist is dropped.
- Every hypothesis needs at least one supporting fact. When a fact argues against a hypothesis, list it \
under contradicting_fact_ids; that makes the analysis more useful, not weaker.
- You cannot confirm a root cause; only the deterministic signatures can. Set root_cause.status to \
"probable" when one hypothesis is the best explanation, or "insufficient_evidence" when the facts do not \
single one out.
- Express uncertainty through confidence (low, medium, high) instead of hedged wording. High means the \
cited facts leave little room for another explanation.
- If CONFIRMED already explains the failure, do not repeat it. Add only hypotheses about contributing \
factors, or about what the confirmed cause leaves unexplained. Returning no hypotheses is a valid answer.
- In evidence_gaps, say which recorded data is missing that would let someone be more certain, for \
example an untraced call, a truncated payload or too few baseline runs.
- Do not invent values, steps, timings or log lines. If something is not in FACTS or TRACE, you do not \
know it.

Write for the developer who will act on this: specific, plain and short.\
"""

PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["hypotheses", "recommendations", "root_cause", "evidence_gaps"],
    "properties": {
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "statement",
                    "confidence",
                    "reasoning",
                    "supporting_fact_ids",
                    "contradicting_fact_ids",
                    "relevant_step_ids",
                ],
                "properties": {
                    "statement": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "reasoning": {"type": "string"},
                    "supporting_fact_ids": {"type": "array", "items": {"type": "string"}},
                    "contradicting_fact_ids": {"type": "array", "items": {"type": "string"}},
                    "relevant_step_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["action", "rationale", "hypothesis_index"],
                "properties": {
                    "action": {"type": "string"},
                    "rationale": {"type": "string"},
                    "hypothesis_index": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                },
            },
        },
        "root_cause": {
            "type": "object",
            "additionalProperties": False,
            "required": ["hypothesis_index", "status"],
            "properties": {
                "hypothesis_index": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "status": {"type": "string", "enum": ["probable", "insufficient_evidence"]},
            },
        },
        "evidence_gaps": {"type": "array", "items": {"type": "string"}},
    },
}


def _short(value: Any) -> str | None:
    if value is None:
        return None
    text = json_excerpt(value)
    return text if len(text) <= DIGEST_VALUE_CHARS else text[:DIGEST_VALUE_CHARS] + "…"


def build_digest(context: InvestigationContext) -> dict[str, Any]:
    """The run in a few kilobytes: every step's identity and outcome, with shortened inputs and outputs."""
    execution, steps = context.execution, list(context.steps)
    omitted = 0
    if len(steps) > DIGEST_MAX_STEPS:
        omitted = len(steps) - DIGEST_MAX_STEPS
        steps = steps[:20] + steps[-40:]
    ordinal_by_id = {step.id: step.ordinal for step in context.steps}
    return {
        "execution": {
            "agent": context.agent_slug,
            "status": execution.status,
            "duration_ms": execution.duration_ms,
            "step_count": execution.step_count,
            "error": execution.error and {key: execution.error.get(key) for key in ("type", "message")},
            "expected_steps": execution.config.get("expected_steps"),
            "input": _short(execution.input),
            "output": _short(execution.output),
        },
        "steps_omitted_from_the_middle": omitted,
        "steps": [
            {
                "step_id": step.id,
                "ordinal": step.ordinal,
                "parent_ordinal": ordinal_by_id.get(step.parent_step_id),
                "name": step.name,
                "type": step.type,
                "status": step.status,
                "attempt": step.attempt,
                "tool_name": step.tool_name,
                "model": step.model,
                "duration_ms": step.duration_ms,
                "error": step.error and {key: step.error.get(key) for key in ("type", "message")},
                "input": _short(step.input),
                "output": _short(step.output),
            }
            for step in steps
        ],
    }


def build_user_message(
    facts: list[dict[str, Any]], digest: dict[str, Any], confirmed: list[dict[str, Any]]
) -> str:
    def block(title: str, value: Any) -> str:
        return f"<{title}>\n{json.dumps(value, ensure_ascii=False, indent=1)}\n</{title}>"

    return "\n\n".join([block("FACTS", facts), block("TRACE", digest), block("CONFIRMED", confirmed)])
