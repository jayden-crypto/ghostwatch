from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import PageDep, SessionDep
from app.api.responses import errors
from app.schemas.anomalies import Anomaly
from app.schemas.common import Page
from app.services import anomalies as service

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get(
    "",
    response_model=Page[Anomaly],
    responses=errors(400, 422),
    summary="List anomalies with their evidence",
)
def list_anomalies(
    session: SessionDep,
    page: PageDep,
    agent_id: str | None = None,
    execution_id: str | None = None,
    type: Annotated[str | None, Query(description="Comma-separated anomaly types")] = None,
    severity: Annotated[str | None, Query(description="Comma-separated severities")] = None,
    status: Annotated[str | None, Query(description="Comma-separated statuses")] = None,
    sort: Annotated[str, Query(description="detected_at; prefix with - for descending")] = "-detected_at",
) -> Page[Anomaly]:
    """Anomalies are raised by deterministic rules when an execution ends.

    `explanation` states the observed value, the baseline figures and the threshold that was
    crossed. Each `evidence` item points at a stored step or execution through `ref_id` and copies
    the value it found there.
    """
    return service.list_anomalies(
        session,
        agent_id=agent_id,
        execution_id=execution_id,
        type=type,
        severity=severity,
        status=status,
        sort=sort,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{anomaly_id}", response_model=Anomaly, responses=errors(404), summary="Get one anomaly")
def get_anomaly(anomaly_id: str, session: SessionDep) -> Anomaly:
    """One anomaly with its explanation and evidence."""
    return service.build_anomalies(session, [service.get_anomaly(session, anomaly_id)])[0]
