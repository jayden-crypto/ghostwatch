from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Response

from app.api.deps import PageDep, SessionDep, SessionFactoryDep
from app.schemas.common import ContractModel, Page
from app.schemas.investigations import Investigation
from app.services import investigations as service
from app.services.investigation import engine

router = APIRouter(prefix="/investigations", tags=["investigations"])


class InvestigationRequest(ContractModel):
    force: bool = False


@router.get("", response_model=Page[Investigation], summary="List investigations with their reports")
def list_investigations(
    session: SessionDep,
    page: PageDep,
    status: Annotated[str | None, Query(description="Comma-separated investigation statuses")] = None,
    agent_id: str | None = None,
    sort: Annotated[str, Query(description="created_at; prefix with - for descending")] = "-created_at",
) -> Page[Investigation]:
    return service.list_investigations(
        session, status=status, agent_id=agent_id, sort=sort, limit=page.limit, offset=page.offset
    )


@router.post(
    "/{execution_id}",
    response_model=Investigation,
    status_code=202,
    responses={200: {"model": Investigation, "description": "A completed investigation already exists."}},
    summary="Investigate an execution (runs in the background)",
)
def request_investigation(
    execution_id: str,
    response: Response,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    background_tasks: BackgroundTasks,
    body: InvestigationRequest | None = None,
) -> Investigation:
    investigation, queued = service.request(session, execution_id, force=bool(body and body.force))
    if queued:
        background_tasks.add_task(engine.run, investigation.id, session_factory)
    response.status_code = 200 if investigation.status == "completed" else 202
    return service.to_schema(investigation)


@router.get("/{execution_id}", response_model=Investigation, summary="Latest investigation of an execution")
def get_investigation(execution_id: str, session: SessionDep) -> Investigation:
    return service.to_schema(service.get_latest(session, execution_id))
