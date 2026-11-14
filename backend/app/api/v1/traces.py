from fastapi import APIRouter

from app.api.deps import PageDep, SessionDep
from app.schemas.common import Page
from app.schemas.events import StoredEvent
from app.schemas.traces import Trace
from app.services import traces as service

router = APIRouter(prefix="/executions", tags=["traces"])


@router.get("/{execution_id}/trace", response_model=Trace, summary="Execution, derived steps and anomalies")
def get_trace(execution_id: str, session: SessionDep) -> Trace:
    return service.get_trace(session, execution_id)


@router.get(
    "/{execution_id}/events",
    response_model=Page[StoredEvent],
    summary="Raw event log in seq order (the evidence behind the trace)",
)
def list_events(execution_id: str, session: SessionDep, page: PageDep) -> Page[StoredEvent]:
    return service.list_events(session, execution_id, limit=page.limit, offset=page.offset)
