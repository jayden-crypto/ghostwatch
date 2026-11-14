from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import PageDep, SessionDep
from app.schemas.anomalies import Anomaly
from app.schemas.common import Page
from app.services import anomalies as service

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("", response_model=Page[Anomaly], summary="List anomalies with their evidence")
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


@router.get("/{anomaly_id}", response_model=Anomaly, summary="Get one anomaly")
def get_anomaly(anomaly_id: str, session: SessionDep) -> Anomaly:
    return service.build_anomalies(session, [service.get_anomaly(session, anomaly_id)])[0]
