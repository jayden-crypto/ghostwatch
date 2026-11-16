"""Contract §3: Agents."""

from typing import Annotated

from pydantic import StringConstraints

from app.schemas.common import AgentId, ContractModel, Json, Timestamp
from app.schemas.enums import AgentHealth
from app.schemas.executions import ExecutionSummary

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]+$", max_length=100)]
Name = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class AgentStats(ContractModel):
    total_executions: int
    completed: int
    failed: int
    timed_out: int
    running: int
    success_rate: float | None
    avg_duration_ms: int | None
    open_anomalies: int
    last_execution: ExecutionSummary | None
    health: AgentHealth


class Agent(ContractModel):
    id: AgentId
    name: str
    slug: str
    description: str | None
    framework: str | None
    metadata: dict[str, Json]
    created_at: Timestamp
    stats: AgentStats


class AgentUpsert(ContractModel):
    """Body of POST /agents. Fields left out of an update keep their stored value."""

    name: Name
    slug: Slug
    description: str | None = None
    framework: str | None = None
    metadata: dict[str, Json] | None = None
