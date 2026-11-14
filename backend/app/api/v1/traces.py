from fastapi import APIRouter

from app.api.deps import PageDep, SessionDep
from app.api.responses import errors
from app.schemas.common import Page
from app.schemas.events import StoredEvent
from app.schemas.traces import Trace
from app.services import traces as service

router = APIRouter(prefix="/executions", tags=["traces"])


@router.get(
    "/{execution_id}/trace",
    response_model=Trace,
    responses=errors(404),
    summary="Execution, derived steps and anomalies",
)
def get_trace(execution_id: str, session: SessionDep) -> Trace:
    """The steps as a flat list sorted by `ordinal`; build the tree from `parent_step_id`.

    `depth` and `offset_ms` (start relative to the execution's start) are computed here, so a
    waterfall needs no clock arithmetic. A step still in flight has `status: running` and null
    `ended_at` and `duration_ms`.
    """
    return service.get_trace(session, execution_id)


@router.get(
    "/{execution_id}/events",
    response_model=Page[StoredEvent],
    responses=errors(404, 422),
    summary="Raw event log in seq order (the evidence behind the trace)",
)
def list_events(execution_id: str, session: SessionDep, page: PageDep) -> Page[StoredEvent]:
    """The append-only record every step, anomaly and investigation is derived from, exactly as stored."""
    return service.list_events(session, execution_id, limit=page.limit, offset=page.offset)
