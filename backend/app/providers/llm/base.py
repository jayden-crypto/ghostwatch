"""The provider interface: one method that turns facts and a trace digest into proposed hypotheses.

A provider only proposes. Its output is validated here, and every citation in it is checked by
`services/investigation/verify.py` before anything reaches a report.
"""

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ProposedHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    confidence: Literal["low", "medium", "high"]
    reasoning: str
    supporting_fact_ids: list[str]
    contradicting_fact_ids: list[str] = Field(default_factory=list)
    relevant_step_ids: list[str] = Field(default_factory=list)


class ProposedRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    rationale: str
    hypothesis_index: int | None = None  # index into `hypotheses`


class ProposedRootCause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_index: int | None = None
    # Free text on purpose: a provider claiming "confirmed" must be caught and downgraded, not rejected.
    status: str = "probable"


class Proposal(BaseModel):
    """What a provider returns. Indexes refer to positions in `hypotheses`."""

    model_config = ConfigDict(extra="forbid")

    hypotheses: list[ProposedHypothesis] = Field(default_factory=list)
    recommendations: list[ProposedRecommendation] = Field(default_factory=list)
    root_cause: ProposedRootCause = Field(default_factory=ProposedRootCause)
    evidence_gaps: list[str] = Field(default_factory=list)


class ProviderResult(BaseModel):
    proposal: Proposal
    model: str | None  # the model that actually produced the proposal
    raw: Any = None  # the provider's raw response, kept for audit and never returned by the API


class ProviderError(Exception):
    """The provider could not produce a usable proposal. `reason` is shown in the report."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LLMProvider(Protocol):
    name: Literal["fable", "rule_based"]

    def investigate(
        self, facts: list[dict[str, Any]], digest: dict[str, Any], confirmed: list[dict[str, Any]]
    ) -> ProviderResult:
        """Propose hypotheses and recommendations that cite the given facts and step ids.

        `confirmed` lists root causes the deterministic signatures already established, so a
        provider can add to them instead of repeating them.
        """
        ...
