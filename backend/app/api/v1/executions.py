from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app.api.deps import PageDep, SessionDep, require_api_key
from app.api.responses import errors
from app.schemas.common import Page
from app.schemas.executions import ExecutionCreate, ExecutionDetail, ExecutionSummary
from app.services import executions as service

router = APIRouter(prefix="/executions", tags=["executions"])


@router.post(
    "",
    response_model=ExecutionDetail,
    status_code=201,
    responses=errors(401, (404, "`not_found`: `agent_id` or `replay_of` does not exist."), 422),
    dependencies=[Depends(require_api_key)],
    summary="Start an execution (status: running)",
)
def create_execution(body: ExecutionCreate, session: SessionDep) -> ExecutionDetail:
    """Starts a run in status `running`. Everything after this arrives as events.

    `started_at` defaults to the server's clock. `config.expected_steps` names the steps that must
    complete for the run to count as done (used by the ghost-completion rule), and
    `config.timeout_ms` is how long the run may stay silent before it is timed out (default 300000).
    """
    return service.build_detail(session, service.create_execution(session, body))


@router.get(
    "",
    response_model=Page[ExecutionSummary],
    responses=errors(400, 422),
    summary="List executions with filters",
)
def list_executions(
    session: SessionDep,
    page: PageDep,
    agent_id: str | None = None,
    status: Annotated[str | None, Query(description="Comma-separated execution statuses")] = None,
    started_after: Annotated[AwareDatetime | None, Query(description="Inclusive lower bound")] = None,
    started_before: Annotated[AwareDatetime | None, Query(description="Exclusive upper bound")] = None,
    min_duration_ms: Annotated[int | None, Query(ge=0)] = None,
    max_duration_ms: Annotated[int | None, Query(ge=0)] = None,
    has_anomaly: bool | None = None,
    is_replay: bool | None = None,
    replay_of: str | None = None,
    q: Annotated[str | None, Query(description="Execution id prefix or agent name")] = None,
    sort: Annotated[
        str,
        Query(description="started_at, duration_ms, tokens_total or cost_usd; prefix with - for descending"),
    ] = "-started_at",
) -> Page[ExecutionSummary]:
    """All filters combine with AND. `total` is the number of matches, not the page size.

    Unknown values (a running execution's duration, unreported tokens, unpriced cost) sort last in
    both directions. Duration filters leave out executions that are still running.
    """
    return service.list_executions(
        session,
        agent_id=agent_id,
        status=status,
        started_after=started_after,
        started_before=started_before,
        min_duration_ms=min_duration_ms,
        max_duration_ms=max_duration_ms,
        has_anomaly=has_anomaly,
        is_replay=is_replay,
        replay_of=replay_of,
        q=q,
        sort=sort,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/{execution_id}", response_model=ExecutionDetail, responses=errors(404), summary="Get one execution"
)
def get_execution(execution_id: str, session: SessionDep) -> ExecutionDetail:
    """The execution with its input, output, config and token totals."""
    return service.build_detail(session, service.get_execution(session, execution_id))
