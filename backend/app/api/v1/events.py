from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.deps import SessionDep, SessionFactoryDep, require_api_key
from app.schemas.events import IngestRequest, IngestResponse
from app.services import ingest
from app.services.investigation import engine as investigation_engine

router = APIRouter(prefix="/executions", tags=["events"])


@router.post(
    "/{execution_id}/events",
    response_model=IngestResponse,
    status_code=202,
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
    result = ingest.ingest_events(session, execution_id, body.events)
    if result.investigation_id is not None:
        # Queued in the same transaction as the terminal event; it runs once the response is sent.
        background_tasks.add_task(investigation_engine.run, result.investigation_id, session_factory)
    return result.response
