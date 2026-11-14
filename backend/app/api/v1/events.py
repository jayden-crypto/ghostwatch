from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.deps import SessionDep, SessionFactoryDep, require_api_key
from app.api.responses import errors
from app.schemas.events import IngestRequest, IngestResponse
from app.services import ingest
from app.services.investigation import engine as investigation_engine

router = APIRouter(prefix="/executions", tags=["events"])


@router.post(
    "/{execution_id}/events",
    response_model=IngestResponse,
    status_code=202,
    responses=errors(
        401,
        404,
        (
            409,
            "`execution_already_terminal`: the execution has ended and the batch holds a new non-log event.",
        ),
        (422, "`validation_error`: a malformed event, or a step event for a step that cannot take it."),
    ),
    dependencies=[Depends(require_api_key)],
    summary="Ingest a batch of events (idempotent per execution and seq)",
)
def ingest_events(
    execution_id: str,
    body: IngestRequest,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    background_tasks: BackgroundTasks,
) -> IngestResponse:
    """Stores 1 to 500 events and derives steps, status and totals from them in one transaction.

    Events are applied in `seq` order whatever their order in the batch. A `seq` that is already
    stored is counted in `duplicates` and skipped, so resending a batch is always safe. A batch is
    all-or-nothing: if any event is rejected, none is stored.

    A terminal event (`execution.completed`, `execution.failed`, `execution.timed_out`) sets the end
    time, duration and token totals, runs the anomaly rules, and queues an investigation when the
    run failed, timed out, or raised an anomaly of high severity or above.
    """
    result = ingest.ingest_events(session, execution_id, body.events)
    if result.investigation_id is not None:
        # Queued in the same transaction as the terminal event; it runs once the response is sent.
        background_tasks.add_task(investigation_engine.run, result.investigation_id, session_factory)
    return result.response
