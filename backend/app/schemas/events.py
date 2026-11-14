"""Contract §5: event ingestion."""

from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import ContractModel, EventId, Json, StepId, Timestamp
from app.schemas.common import InputTimestamp as EventTime
from app.schemas.enums import EventType, ExecutionStatus, StepType


class ErrorInfoInput(ContractModel):
    type: str
    message: str
    stacktrace: str | None = None


class StepStartedPayload(ContractModel):
    step_id: StepId
    parent_step_id: StepId | None = None
    name: str = Field(min_length=1)
    step_type: StepType
    input: Json = None
    tool_name: str | None = None
    model: str | None = None
    attempt: int = Field(default=1, ge=1)
    metadata: dict[str, Json] = Field(default_factory=dict)


class StepCompletedPayload(ContractModel):
    step_id: StepId
    output: Json = None
    tokens_input: int | None = Field(default=None, ge=0)
    tokens_output: int | None = Field(default=None, ge=0)
    metadata: dict[str, Json] = Field(default_factory=dict)


class StepFailedPayload(ContractModel):
    step_id: StepId
    error: ErrorInfoInput
    output: Json = None


class ExecutionCompletedPayload(ContractModel):
    output: Json = None


class ExecutionFailedPayload(ContractModel):
    error: ErrorInfoInput


class ExecutionTimedOutPayload(ContractModel):
    pass


class LogPayload(ContractModel):
    level: Literal["debug", "info", "warning", "error"]
    message: str
    step_id: StepId | None = None


class _Event(ContractModel):
    seq: int = Field(ge=1)
    timestamp: EventTime


class StepStarted(_Event):
    type: Literal["step.started"]
    payload: StepStartedPayload


class StepCompleted(_Event):
    type: Literal["step.completed"]
    payload: StepCompletedPayload


class StepFailed(_Event):
    type: Literal["step.failed"]
    payload: StepFailedPayload


class ExecutionCompleted(_Event):
    type: Literal["execution.completed"]
    payload: ExecutionCompletedPayload


class ExecutionFailed(_Event):
    type: Literal["execution.failed"]
    payload: ExecutionFailedPayload


class ExecutionTimedOut(_Event):
    type: Literal["execution.timed_out"]
    payload: ExecutionTimedOutPayload


class Log(_Event):
    type: Literal["log"]
    payload: LogPayload


IngestEvent = Annotated[
    StepStarted | StepCompleted | StepFailed | ExecutionCompleted | ExecutionFailed | ExecutionTimedOut | Log,
    Field(discriminator="type"),
]


class IngestRequest(ContractModel):
    events: list[IngestEvent] = Field(min_length=1, max_length=500)


class IngestResponse(ContractModel):
    accepted: int
    duplicates: int
    execution_status: ExecutionStatus


class StoredEvent(ContractModel):
    """One row of the raw evidence view (GET /executions/{id}/events)."""

    id: EventId
    seq: int
    type: EventType
    timestamp: Timestamp
    received_at: Timestamp
    payload: dict[str, Json]
