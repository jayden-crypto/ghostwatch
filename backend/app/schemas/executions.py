"""Contract §4: Executions."""

from typing import Any, Self

from pydantic import ConfigDict, Field, model_validator

from app.schemas.common import (
    AgentId,
    ContractModel,
    ErrorInfo,
    ExecutionId,
    InputTimestamp,
    Json,
    ReplayId,
    Timestamp,
)
from app.schemas.enums import ExecutionStatus


class ExecutionSummary(ContractModel):
    id: ExecutionId
    agent_id: AgentId
    agent_name: str
    status: ExecutionStatus
    started_at: Timestamp
    ended_at: Timestamp | None
    duration_ms: int | None
    step_count: int
    tokens_total: int | None
    cost_usd: float | None
    anomaly_count: int
    has_investigation: bool
    replay_of: ExecutionId | None
    error: ErrorInfo | None


class ExecutionConfig(ContractModel):
    """The four known keys are always present; free-form extras are allowed and preserved."""

    model_config = ConfigDict(extra="allow")

    model: str | None
    params: dict[str, Json]
    expected_steps: list[str] | None
    timeout_ms: int | None


class ExecutionDetail(ExecutionSummary):
    input: Json
    output: Json
    config: ExecutionConfig
    tokens_input: int | None
    tokens_output: int | None
    tags: list[str]
    replay_ids: list[ReplayId]


class ExecutionConfigInput(ContractModel):
    """Request form of ExecutionConfig: every known key is optional."""

    model_config = ConfigDict(extra="allow")

    model: str | None = None
    params: dict[str, Json] = Field(default_factory=dict)
    expected_steps: list[str] | None = None
    timeout_ms: int | None = Field(default=None, gt=0)


class ExecutionCreate(ContractModel):
    agent_id: AgentId
    input: Json = None
    config: ExecutionConfigInput = Field(default_factory=ExecutionConfigInput)
    tags: list[str] = Field(default_factory=list)
    started_at: InputTimestamp | None = None
    replay_of: ExecutionId | None = None
    replay_id: ReplayId | None = None

    @model_validator(mode="after")
    def _replay_id_needs_replay_of(self) -> Self:
        if self.replay_id is not None and self.replay_of is None:
            raise ValueError("replay_id requires replay_of")
        return self

    def stored_config(self) -> dict[str, Any]:
        return self.config.model_dump()
