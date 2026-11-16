"""Contract §9: Investigations."""

from typing import Annotated, Self

from pydantic import Field, StringConstraints, model_validator

from app.schemas.common import (
    ContractModel,
    ErrorInfo,
    Evidence,
    ExecutionId,
    InvestigationId,
    StepId,
    Timestamp,
)
from app.schemas.enums import (
    Confidence,
    InvestigationProvider,
    InvestigationStatus,
    InvestigationTrigger,
    RootCauseStatus,
)

FactId = Annotated[str, StringConstraints(pattern=r"^F[1-9]\d*$")]
HypothesisId = Annotated[str, StringConstraints(pattern=r"^H[1-9]\d*$")]
RecommendationId = Annotated[str, StringConstraints(pattern=r"^R[1-9]\d*$")]


class Fact(ContractModel):
    id: FactId
    statement: str
    evidence: list[Evidence] = Field(min_length=1)


class Hypothesis(ContractModel):
    id: HypothesisId
    statement: str
    confidence: Confidence
    reasoning: str
    supporting_fact_ids: list[FactId] = Field(min_length=1)
    contradicting_fact_ids: list[FactId]


class Recommendation(ContractModel):
    id: RecommendationId
    action: str
    rationale: str
    hypothesis_id: HypothesisId | None


class RootCause(ContractModel):
    status: RootCauseStatus
    statement: str
    hypothesis_id: HypothesisId | None
    signature: str | None

    @model_validator(mode="after")
    def _status_matches_references(self) -> Self:
        if (self.status == "confirmed") != (self.signature is not None):
            raise ValueError("signature is set exactly when status is 'confirmed'")
        if self.status == "insufficient_evidence" and self.hypothesis_id is not None:
            raise ValueError("hypothesis_id must be null when status is 'insufficient_evidence'")
        return self


class InvestigationReport(ContractModel):
    summary: str
    failing_step_id: StepId | None
    root_cause: RootCause
    facts: list[Fact]
    hypotheses: list[Hypothesis]
    recommendations: list[Recommendation]
    evidence_gaps: list[str]
    relevant_step_ids: list[StepId]

    @model_validator(mode="after")
    def _citations_resolve(self) -> Self:
        """Every id a report cites must exist inside the same report."""
        fact_ids = [fact.id for fact in self.facts]
        hypothesis_ids = [hypothesis.id for hypothesis in self.hypotheses]
        if len(set(fact_ids)) != len(fact_ids) or len(set(hypothesis_ids)) != len(hypothesis_ids):
            raise ValueError("fact and hypothesis ids must be unique within a report")
        for hypothesis in self.hypotheses:
            cited = [*hypothesis.supporting_fact_ids, *hypothesis.contradicting_fact_ids]
            unknown = sorted(set(cited) - set(fact_ids))
            if unknown:
                raise ValueError(f"hypothesis {hypothesis.id} cites facts that do not exist: {unknown}")
        for recommendation in self.recommendations:
            if (
                recommendation.hypothesis_id is not None
                and recommendation.hypothesis_id not in hypothesis_ids
            ):
                raise ValueError(f"recommendation {recommendation.id} cites a hypothesis that does not exist")
        if self.root_cause.hypothesis_id is not None and self.root_cause.hypothesis_id not in hypothesis_ids:
            raise ValueError("root_cause cites a hypothesis that does not exist")
        return self


class Investigation(ContractModel):
    id: InvestigationId
    execution_id: ExecutionId
    status: InvestigationStatus
    trigger: InvestigationTrigger
    provider: InvestigationProvider
    model: str | None
    created_at: Timestamp
    completed_at: Timestamp | None
    error: ErrorInfo | None
    report: InvestigationReport | None

    @model_validator(mode="after")
    def _report_only_when_completed(self) -> Self:
        if (self.status == "completed") != (self.report is not None):
            raise ValueError("report is set exactly when status is 'completed'")
        return self
