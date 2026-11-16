"""The honesty rules (contract §9), enforced on whatever a provider returns.

1. Only the deterministic signature matcher may say `confirmed`: a provider's "confirmed" becomes `probable`.
2. A hypothesis citing a fact id that does not exist, or a step id that is not in the trace, is dropped
   and a note is added to the evidence gaps.
3. If no hypothesis survives, the provider contributes no root cause.
"""

from dataclasses import dataclass, field
from typing import Any

from app.providers.llm.base import Proposal

MAX_GAPS_FROM_PROVIDER = 8
MAX_TEXT = 2000


@dataclass
class Verified:
    hypotheses: list[dict[str, Any]] = field(default_factory=list)  # contract Hypothesis objects
    recommendations: list[dict[str, Any]] = field(
        default_factory=list
    )  # without ids; the engine numbers them
    step_ids: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    root_hypothesis_id: str | None = None  # the provider's root cause, always at most `probable`


def _text(value: str) -> str:
    return value.strip()[:MAX_TEXT]


def verify(
    proposal: Proposal, *, fact_ids: set[str], step_ids: set[str], source: str, first_number: int
) -> Verified:
    """Keep only what the recorded evidence supports. `source` names the provider in gap notes."""
    verified = Verified()
    kept: dict[int, str] = {}  # index in the proposal -> assigned hypothesis id

    for index, hypothesis in enumerate(proposal.hypotheses):
        cited_facts = [*hypothesis.supporting_fact_ids, *hypothesis.contradicting_fact_ids]
        unknown_facts = sorted(set(cited_facts) - fact_ids)
        unknown_steps = sorted(set(hypothesis.relevant_step_ids) - step_ids)
        problems = []
        if unknown_facts:
            problems.append(f"cited fact id(s) that do not exist ({', '.join(unknown_facts)})")
        if unknown_steps:
            problems.append(f"cited step id(s) that are not in the trace ({', '.join(unknown_steps)})")
        if not hypothesis.supporting_fact_ids:
            problems.append("cited no supporting fact")
        if not hypothesis.statement.strip():
            problems.append("had no statement")
        if problems:
            verified.gaps.append(
                f"A hypothesis proposed by {source} was discarded because it {' and '.join(problems)}."
            )
            continue
        hypothesis_id = f"H{first_number + len(verified.hypotheses)}"
        kept[index] = hypothesis_id
        verified.hypotheses.append(
            {
                "id": hypothesis_id,
                "statement": _text(hypothesis.statement),
                "confidence": hypothesis.confidence,
                "reasoning": _text(hypothesis.reasoning),
                "supporting_fact_ids": list(dict.fromkeys(hypothesis.supporting_fact_ids)),
                "contradicting_fact_ids": list(dict.fromkeys(hypothesis.contradicting_fact_ids)),
            }
        )
        verified.step_ids.extend(hypothesis.relevant_step_ids)

    for recommendation in proposal.recommendations:
        index = recommendation.hypothesis_index
        if index is not None and index not in kept:
            continue  # it argued from a hypothesis that was discarded or never existed
        if not recommendation.action.strip():
            continue
        verified.recommendations.append(
            {
                "action": _text(recommendation.action),
                "rationale": _text(recommendation.rationale),
                "hypothesis_id": None if index is None else kept[index],
            }
        )

    claimed = proposal.root_cause
    if claimed.status == "confirmed":
        verified.gaps.append(
            f"{source} labelled its root cause as confirmed. Only a deterministic signature can confirm a "
            "root cause, so it is reported as a hypothesis."
        )
    if kept and claimed.status != "insufficient_evidence":
        verified.root_hypothesis_id = kept.get(claimed.hypothesis_index) or next(iter(kept.values()))

    for gap in proposal.evidence_gaps[:MAX_GAPS_FROM_PROVIDER]:
        if gap.strip():
            verified.gaps.append(_text(gap))
    return verified
