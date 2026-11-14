from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Response

from app.api.deps import PageDep, SessionDep, SessionFactoryDep
from app.api.responses import errors
from app.schemas.common import ContractModel, Page
from app.schemas.investigations import Investigation
from app.services import investigations as service
from app.services.investigation import engine

router = APIRouter(prefix="/investigations", tags=["investigations"])


class InvestigationRequest(ContractModel):
    force: bool = False


@router.get(
    "",
    response_model=Page[Investigation],
    responses=errors(400, 422),
    summary="List investigations with their reports",
)
def list_investigations(
    session: SessionDep,
    page: PageDep,
    status: Annotated[str | None, Query(description="Comma-separated investigation statuses")] = None,
    agent_id: str | None = None,
    sort: Annotated[str, Query(description="created_at; prefix with - for descending")] = "-created_at",
) -> Page[Investigation]:
    """Investigations, newest first, each with its full report when it has completed."""
    return service.list_investigations(
        session, status=status, agent_id=agent_id, sort=sort, limit=page.limit, offset=page.offset
    )


@router.post(
    "/{execution_id}",
    response_model=Investigation,
    status_code=202,
    responses={
        200: {
            "model": Investigation,
            "description": "A completed investigation exists and `force` is not set.",
        },
        **errors(404, (409, "`conflict`: the execution is still running."), 422),
    },
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
    """Queues an investigation and returns it at once (202). Poll the GET until it leaves queued/running.

    If one is already queued or running it is returned instead of starting another. If a completed
    one exists it is returned with 200, unless the body is `{"force": true}`.

    In a report, facts and their evidence are produced by code from stored data. Hypotheses come
    from the provider and must cite those facts. `root_cause.status` is `confirmed` only when a
    deterministic signature matched; a model's hypothesis is `probable` at most.
    """
    investigation, queued = service.request(session, execution_id, force=bool(body and body.force))
    if queued:
        background_tasks.add_task(engine.run, investigation.id, session_factory)
    response.status_code = 200 if investigation.status == "completed" else 202
    return service.to_schema(investigation)


@router.get(
    "/{execution_id}",
    response_model=Investigation,
    responses=errors((404, "`not_found`: the execution does not exist, or has not been investigated.")),
    summary="Latest investigation of an execution",
)
def get_investigation(execution_id: str, session: SessionDep) -> Investigation:
    """The most recent investigation of the execution. `report` is null until `status` is `completed`."""
    return service.to_schema(service.get_latest(session, execution_id))
