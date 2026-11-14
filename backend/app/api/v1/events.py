from fastapi import APIRouter, Depends

from app.api.deps import SessionDep, require_api_key
from app.schemas.events import IngestRequest, IngestResponse
from app.services import ingest

router = APIRouter(prefix="/executions", tags=["events"])


@router.post(
    "/{execution_id}/events",
    response_model=IngestResponse,
    status_code=202,
    dependencies=[Depends(require_api_key)],
    summary="Ingest a batch of events (idempotent per execution and seq)",
)
def ingest_events(execution_id: str, body: IngestRequest, session: SessionDep) -> IngestResponse:
    return ingest.ingest_events(session, execution_id, body.events)
