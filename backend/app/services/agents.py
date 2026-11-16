"""Agents: idempotent registration, and stats and health computed from stored executions and anomalies."""

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.orm import Session

from app import ids
from app.errors import not_found
from app.models import Agent, Anomaly, Execution
from app.schemas import agents as schemas
from app.schemas.common import Page
from app.schemas.enums import AGENT_HEALTHS, TERMINAL_STATUSES, AgentHealth
from app.services.executions import build_summaries
from app.services.query import contains, parse_csv, parse_sort
from app.timeutil import utcnow

# Contract §3: health is judged over the agent's most recent terminal executions.
HEALTH_WINDOW = 20
FAILING_BELOW = 0.5
DEGRADED_BELOW = 0.9

SORTABLE = {"name": Agent.name, "created_at": Agent.created_at}


def compute_health(
    total_executions: int, recent_success_rate: float | None, open_critical: bool, open_high: bool
) -> AgentHealth:
    if total_executions == 0:
        return "idle"
    if open_critical or (recent_success_rate is not None and recent_success_rate < FAILING_BELOW):
        return "failing"
    if open_high or (recent_success_rate is not None and recent_success_rate < DEGRADED_BELOW):
        return "degraded"
    return "healthy"


def upsert_agent(session: Session, body: schemas.AgentUpsert) -> tuple[Agent, bool]:
    """Register an agent by slug. Returns the agent and whether it was created."""
    created_id = session.scalar(
        insert(Agent)
        .values(
            id=ids.new_id(ids.AGENT),
            slug=body.slug,
            name=body.name,
            description=body.description,
            framework=body.framework,
            metadata_=body.metadata or {},
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=[Agent.slug])
        .returning(Agent.id)
    )
    agent = session.scalars(select(Agent).where(Agent.slug == body.slug)).one()
    if created_id is None:
        for field in body.model_fields_set - {"slug"}:
            value = getattr(body, field)
            if field == "metadata":
                agent.metadata_ = value or {}
            else:
                setattr(agent, field, value)
    session.commit()
    return agent, created_id is not None


def get_agent(session: Session, agent_id: str) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise not_found("Agent", agent_id)
    return agent


def list_agents(
    session: Session, *, q: str | None, health: str | None, sort: str, limit: int, offset: int
) -> Page[schemas.Agent]:
    wanted_health = parse_csv(health, AGENT_HEALTHS, "health")
    query = select(Agent).order_by(parse_sort(sort, SORTABLE), Agent.id)
    if q:
        query = query.where(or_(contains(Agent.name, q), contains(Agent.slug, q)))
    # Health is computed, not stored, so it is filtered after the stats are built. Agents are few.
    agents = build_agents(session, session.scalars(query).all())
    if wanted_health is not None:
        agents = [agent for agent in agents if agent.stats.health in wanted_health]
    return Page(items=agents[offset : offset + limit], total=len(agents), limit=limit, offset=offset)


def build_agents(session: Session, agents: Sequence[Agent]) -> list[schemas.Agent]:
    if not agents:
        return []
    agent_ids = [agent.id for agent in agents]

    status_counts: dict[str, dict[str, int]] = {agent_id: {} for agent_id in agent_ids}
    for agent_id, status, count in session.execute(
        select(Execution.agent_id, Execution.status, func.count())
        .where(Execution.agent_id.in_(agent_ids))
        .group_by(Execution.agent_id, Execution.status)
    ):
        status_counts[agent_id][status] = count

    average_durations = dict(
        session.execute(
            select(Execution.agent_id, func.avg(Execution.duration_ms))
            .where(Execution.agent_id.in_(agent_ids), Execution.status.in_(TERMINAL_STATUSES))
            .group_by(Execution.agent_id)
        ).all()
    )

    open_anomalies: dict[str, dict[str, int]] = {agent_id: {} for agent_id in agent_ids}
    for agent_id, severity, count in session.execute(
        select(Anomaly.agent_id, Anomaly.severity, func.count())
        .where(Anomaly.agent_id.in_(agent_ids), Anomaly.status == "open")
        .group_by(Anomaly.agent_id, Anomaly.severity)
    ):
        open_anomalies[agent_id][severity] = count

    ranked = (
        select(
            Execution.agent_id,
            Execution.status,
            func.row_number()
            .over(
                partition_by=Execution.agent_id, order_by=(Execution.started_at.desc(), Execution.id.desc())
            )
            .label("recency"),
        )
        .where(Execution.agent_id.in_(agent_ids), Execution.status.in_(TERMINAL_STATUSES))
        .subquery()
    )
    recent_success_rates = {
        agent_id: completed / total
        for agent_id, completed, total in session.execute(
            select(
                ranked.c.agent_id,
                func.count().filter(ranked.c.status == "completed"),
                func.count(),
            )
            .where(ranked.c.recency <= HEALTH_WINDOW)
            .group_by(ranked.c.agent_id)
        )
    }

    latest = session.scalars(
        select(Execution)
        .where(Execution.agent_id.in_(agent_ids))
        .ext(distinct_on(Execution.agent_id))
        .order_by(Execution.agent_id, Execution.started_at.desc(), Execution.id.desc())
    ).all()
    last_executions = {summary.agent_id: summary for summary in build_summaries(session, latest)}

    result = []
    for agent in agents:
        counts = status_counts[agent.id]
        completed, failed, timed_out = (counts.get(status, 0) for status in TERMINAL_STATUSES)
        terminal = completed + failed + timed_out
        total = terminal + counts.get("running", 0)
        severities = open_anomalies[agent.id]
        average = average_durations.get(agent.id)
        result.append(
            schemas.Agent(
                id=agent.id,
                name=agent.name,
                slug=agent.slug,
                description=agent.description,
                framework=agent.framework,
                metadata=agent.metadata_,
                created_at=agent.created_at,
                stats=schemas.AgentStats(
                    total_executions=total,
                    completed=completed,
                    failed=failed,
                    timed_out=timed_out,
                    running=counts.get("running", 0),
                    success_rate=completed / terminal if terminal else None,
                    avg_duration_ms=None if average is None else round(average),
                    open_anomalies=sum(severities.values()),
                    last_execution=last_executions.get(agent.id),
                    health=compute_health(
                        total,
                        recent_success_rates.get(agent.id),
                        open_critical=severities.get("critical", 0) > 0,
                        open_high=severities.get("high", 0) > 0,
                    ),
                ),
            )
        )
    return result
