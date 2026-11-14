"""The investigation pipeline: facts -> signatures -> provider -> verify -> report (PROJECT_PLAN §4).

Facts and evidence come from code. A provider may add hypotheses, and only verified ones are kept.
Only a signature match can make the root cause `confirmed`.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import ids
from app.config import Settings, get_settings
from app.models import Execution, Investigation
from app.providers.llm.base import LLMProvider, ProviderError
from app.providers.llm.rule_based import RuleBasedProvider
from app.schemas.investigations import InvestigationReport
from app.services.investigation.context import InvestigationContext, load_context
from app.services.investigation.facts import FactSet, build_facts, error_text, step_label
from app.services.investigation.prompts import build_digest
from app.services.investigation.signatures import SignatureMatch, match_signatures
from app.services.investigation.verify import verify
from app.timeutil import utcnow

logger = logging.getLogger("ghostwatch")

SessionFactory = Callable[[], AbstractContextManager[Session]]

NO_ROOT_CAUSE = (
    "No deterministic signature matched this execution and no supported hypothesis is available, so the "
    "recorded evidence is not sufficient to name a root cause."
)


def make_provider(settings: Settings) -> tuple[LLMProvider, str | None]:
    """The provider to use, and why it is not the configured one (None when it is)."""
    if settings.llm_provider == "fable":
        if not settings.anthropic_api_key:
            return RuleBasedProvider(), "LLM_PROVIDER is fable but no ANTHROPIC_API_KEY is configured"
        from app.providers.llm.fable import FableProvider

        return FableProvider(settings), None
    return RuleBasedProvider(), None


def _summary(context: InvestigationContext, facts: FactSet, root_status: str, signature: str | None) -> str:
    execution, step = context.execution, facts.failing_step
    if execution.status == "failed" and step is not None:
        what = f"The execution failed at {step_label(step)} with {error_text(step.error)}."
    elif execution.status == "failed":
        what = f"The execution failed with {error_text(execution.error)}; no step recorded the failure."
    elif execution.status == "timed_out" and step is not None:
        what = f"The execution timed out while {step_label(step)} was running."
    elif execution.status == "timed_out":
        what = "The execution timed out; no step was running at the time."
    else:
        types = ", ".join(anomaly.type for anomaly in context.anomalies) or "none"
        what = f"The execution {execution.status}. Anomalies raised on it: {types}."
    verdict = {
        "confirmed": f"The root cause is confirmed by the deterministic signature {signature}.",
        "probable": "The root cause given is a hypothesis; it is not confirmed.",
        "insufficient_evidence": "The recorded evidence is not sufficient to determine a root cause.",
    }[root_status]
    return f"{what} {verdict}"


def _from_signature(match: SignatureMatch, number: int) -> tuple[dict[str, Any], dict[str, Any]]:
    hypothesis = {
        "id": f"H{number}",
        "statement": match.statement,
        "confidence": "high",
        "reasoning": match.reasoning,
        "supporting_fact_ids": match.supporting_fact_ids,
        "contradicting_fact_ids": [],
    }
    recommendation = {"action": match.action, "rationale": match.rationale, "hypothesis_id": hypothesis["id"]}
    return hypothesis, recommendation


def build_report(
    context: InvestigationContext, provider: LLMProvider, unavailable: str | None = None
) -> tuple[InvestigationReport, str, str | None, Any]:
    """Returns the report, the provider that actually contributed, its model, and its raw response."""
    facts = build_facts(context)
    matches = match_signatures(context, facts)
    hypotheses: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    for match in matches:
        hypothesis, recommendation = _from_signature(match, len(hypotheses) + 1)
        hypotheses.append(hypothesis)
        recommendations.append(recommendation)
    step_ids = [step_id for match in matches for step_id in match.step_ids]
    gaps = list(facts.gaps)

    used, model, raw, proposed_root = "rule_based", None, None, None
    if unavailable is not None:
        gaps.append(f"No LLM hypotheses: {unavailable}. This report contains deterministic findings only.")
    elif provider.name != "rule_based":
        confirmed = [{"signature": match.signature, "statement": match.statement} for match in matches]
        try:
            result = provider.investigate(facts.facts, build_digest(context), confirmed)
        except ProviderError as exc:
            logger.warning("Provider %s failed for %s: %s", provider.name, context.execution.id, exc.reason)
            gaps.append(
                f"No LLM hypotheses: the {provider.name} provider {exc.reason}. "
                "This report contains deterministic findings only."
            )
        else:
            checked = verify(
                result.proposal,
                fact_ids={fact["id"] for fact in facts.facts},
                step_ids={step.id for step in context.steps},
                source=result.model or provider.name,
                first_number=len(hypotheses) + 1,
            )
            hypotheses += checked.hypotheses
            recommendations += checked.recommendations
            step_ids += checked.step_ids
            gaps += checked.gaps
            used, model, raw, proposed_root = (
                provider.name,
                result.model,
                result.raw,
                checked.root_hypothesis_id,
            )

    if matches:
        root_cause = {
            "status": "confirmed",
            "statement": matches[0].statement,
            "hypothesis_id": "H1",
            "signature": matches[0].signature,
        }
    elif proposed_root is not None:
        statement = next(h["statement"] for h in hypotheses if h["id"] == proposed_root)
        root_cause = {
            "status": "probable",
            "statement": statement,
            "hypothesis_id": proposed_root,
            "signature": None,
        }
    else:
        root_cause = {
            "status": "insufficient_evidence",
            "statement": NO_ROOT_CAUSE,
            "hypothesis_id": None,
            "signature": None,
        }

    if facts.failing_step is not None:
        step_ids.insert(0, facts.failing_step.id)
    ordinals = {step.id: step.ordinal for step in context.steps}
    report = InvestigationReport.model_validate(
        {
            "summary": _summary(context, facts, root_cause["status"], root_cause["signature"]),
            "failing_step_id": facts.failing_step.id if facts.failing_step is not None else None,
            "root_cause": root_cause,
            "facts": facts.facts,
            "hypotheses": hypotheses,
            "recommendations": [
                {"id": f"R{number}", **recommendation}
                for number, recommendation in enumerate(recommendations, 1)
            ],
            "evidence_gaps": gaps,
            "relevant_step_ids": sorted(
                {step_id for step_id in step_ids if step_id in ordinals}, key=ordinals.get
            ),
        }
    )
    return report, used, model, raw


def queue(session: Session, execution: Execution, trigger: str) -> Investigation:
    """Record an investigation to run. The caller commits and then hands the id to `run`."""
    settings = get_settings()
    uses_fable = settings.llm_provider == "fable" and settings.llm_configured
    investigation = Investigation(
        id=ids.new_id(ids.INVESTIGATION),
        execution_id=execution.id,
        status="queued",
        trigger=trigger,
        provider="fable" if uses_fable else "rule_based",
        model=settings.llm_model if uses_fable else None,
        created_at=utcnow(),
    )
    session.add(investigation)
    session.flush()
    return investigation


def run(investigation_id: str, session_factory: SessionFactory) -> None:
    """Run one queued investigation to completion. Safe to call twice: only one caller claims it."""
    with session_factory() as session:
        claimed = session.scalar(
            update(Investigation)
            .where(Investigation.id == investigation_id, Investigation.status == "queued")
            .values(status="running")
            .returning(Investigation.id)
        )
        session.commit()
        if claimed is None:
            return
        investigation = session.get(Investigation, investigation_id, populate_existing=True)
        try:
            with session.begin_nested():
                execution = session.get(Execution, investigation.execution_id)
                provider, unavailable = make_provider(get_settings())
                report, used, model, raw = build_report(
                    load_context(session, execution), provider, unavailable
                )
                investigation.report = report.model_dump(mode="json")
                investigation.provider = used
                investigation.model = model
                investigation.llm_raw_response = raw
                investigation.status = "completed"
        except Exception as exc:
            logger.exception("Investigation %s failed", investigation_id)
            investigation.status = "failed"
            investigation.error = {
                "type": type(exc).__name__,
                "message": "The investigation could not be completed; see the backend log.",
                "stacktrace": None,
            }
        investigation.completed_at = utcnow()
        session.commit()


def run_queued(session_factory: SessionFactory) -> int:
    """Run every investigation that is still queued (for example after a restart). Returns how many."""
    with session_factory() as session:
        queued = session.scalars(
            select(Investigation.id)
            .where(Investigation.status == "queued")
            .order_by(Investigation.created_at)
        ).all()
    for investigation_id in queued:
        run(investigation_id, session_factory)
    return len(queued)
