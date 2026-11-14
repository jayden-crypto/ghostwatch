"""Contract §6: Traces."""

from app.schemas.anomalies import Anomaly
from app.schemas.common import ContractModel, ErrorInfo, ExecutionId, Json, StepId, Timestamp
from app.schemas.enums import StepStatus, StepType
from app.schemas.executions import ExecutionDetail


class Step(ContractModel):
    id: StepId
    execution_id: ExecutionId
    parent_step_id: StepId | None
    ordinal: int
    depth: int
    name: str
    type: StepType
    status: StepStatus
    started_at: Timestamp
    ended_at: Timestamp | None
    duration_ms: int | None
    offset_ms: int
    input: Json
    output: Json
    error: ErrorInfo | None
    tool_name: str | None
    model: str | None
    tokens_input: int | None
    tokens_output: int | None
    attempt: int
    metadata: dict[str, Json]


class Trace(ContractModel):
    execution: ExecutionDetail
    steps: list[Step]
    anomalies: list[Anomaly]
    event_count: int
