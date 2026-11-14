from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import PageDep, SessionDep, require_api_key
from app.schemas.agents import Agent, AgentUpsert
from app.schemas.common import Page
from app.services import agents as service

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post(
    "",
    response_model=Agent,
    status_code=201,
    responses={200: {"model": Agent, "description": "The slug already existed; the agent was updated."}},
    dependencies=[Depends(require_api_key)],
    summary="Register an agent (idempotent upsert by slug)",
)
def upsert_agent(body: AgentUpsert, response: Response, session: SessionDep) -> Agent:
    agent, created = service.upsert_agent(session, body)
    response.status_code = 201 if created else 200
    return service.build_agents(session, [agent])[0]


@router.get("", response_model=Page[Agent], summary="List agents with stats and health")
def list_agents(
    session: SessionDep,
    page: PageDep,
    q: Annotated[str | None, Query(description="Name or slug contains")] = None,
    health: Annotated[str | None, Query(description="healthy, degraded, failing or idle")] = None,
    sort: Annotated[str, Query(description="name or created_at; prefix with - for descending")] = "name",
) -> Page[Agent]:
    return service.list_agents(session, q=q, health=health, sort=sort, limit=page.limit, offset=page.offset)


@router.get("/{agent_id}", response_model=Agent, summary="Get one agent")
def get_agent(agent_id: str, session: SessionDep) -> Agent:
    return service.build_agents(session, [service.get_agent(session, agent_id)])[0]
