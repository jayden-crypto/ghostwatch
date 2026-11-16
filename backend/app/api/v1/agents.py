from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import PageDep, SessionDep, require_api_key
from app.api.responses import errors
from app.schemas.agents import Agent, AgentUpsert
from app.schemas.common import Page
from app.services import agents as service

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post(
    "",
    response_model=Agent,
    status_code=201,
    responses={
        200: {"model": Agent, "description": "The slug already existed; the agent was updated."},
        **errors(401, 422),
    },
    dependencies=[Depends(require_api_key)],
    summary="Register an agent (idempotent upsert by slug)",
)
def upsert_agent(body: AgentUpsert, response: Response, session: SessionDep) -> Agent:
    """Creates the agent (201) or, if the slug exists, updates it (200). Safe to call on every start.

    On an update, fields left out of the body keep their stored value; an explicit `null` clears one.
    """
    agent, created = service.upsert_agent(session, body)
    response.status_code = 201 if created else 200
    return service.build_agents(session, [agent])[0]


@router.get(
    "",
    response_model=Page[Agent],
    responses=errors(400, 422),
    summary="List agents with stats and health",
)
def list_agents(
    session: SessionDep,
    page: PageDep,
    q: Annotated[str | None, Query(description="Name or slug contains (case-insensitive)")] = None,
    health: Annotated[
        str | None, Query(description="Comma-separated: healthy, degraded, failing, idle")
    ] = None,
    sort: Annotated[str, Query(description="name or created_at; prefix with - for descending")] = "name",
) -> Page[Agent]:
    """Every number in `stats` is computed from stored executions and anomalies.

    `success_rate` and `avg_duration_ms` cover all of the agent's terminal executions and are null
    when it has none. `health` looks at the last 20 terminal executions and at open anomalies:
    `failing` below 50 % success or with an open critical anomaly, `degraded` below 90 % or with an
    open high anomaly, `idle` with no executions, otherwise `healthy`.
    """
    return service.list_agents(session, q=q, health=health, sort=sort, limit=page.limit, offset=page.offset)


@router.get("/{agent_id}", response_model=Agent, responses=errors(404), summary="Get one agent")
def get_agent(agent_id: str, session: SessionDep) -> Agent:
    """The agent with its stats and health, computed as in the list."""
    return service.build_agents(session, [service.get_agent(session, agent_id)])[0]
