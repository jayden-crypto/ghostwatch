"""Contract §10: Replays."""

from typing import Self

from pydantic import model_validator

from app.schemas.common import ContractModel, ErrorInfo, ExecutionId, Json, ReplayId, StepId, Timestamp
from app.schemas.enums import ReplayMode, ReplayOutcome, ReplayStatus, StepChange, StepStatus, StepType
from app.schemas.executions import ExecutionDetail, ExecutionSummary


class RecordedCall(ContractModel):
    step_name: str
    step_type: StepType
    tool_name: str | None
    occurrence: int
    input: Json
    output: Json
    error: ErrorInfo | None


class ReplayBundle(ContractModel):
    original_execution: ExecutionDetail
    recorded_calls: list[RecordedCall]


class StepDiff(ContractModel):
    ordinal: int
    name: str
    original_step_id: StepId | None
    replay_step_id: StepId | None
    change: StepChange
    original_status: StepStatus | None
    replay_status: StepStatus | None


class ReplayComparison(ContractModel):
    original: ExecutionSummary
    replay: ExecutionSummary
    outcome: ReplayOutcome
    duration_delta_ms: int | None
    tokens_delta: int | None
    step_count_delta: int
    step_diffs: list[StepDiff]


class Replay(ContractModel):
    id: ReplayId
    original_execution_id: ExecutionId
    replay_execution_id: ExecutionId | None
    mode: ReplayMode
    status: ReplayStatus
    side_effects_authorized: bool
    note: str | None
    requested_at: Timestamp
    claimed_at: Timestamp | None
    completed_at: Timestamp | None
    error: ErrorInfo | None
    comparison: ReplayComparison | None

    @model_validator(mode="after")
    def _live_requires_authorization(self) -> Self:
        if self.mode == "live" and not self.side_effects_authorized:
            raise ValueError("a live replay cannot exist without side-effect authorization")
        return self


class ReplayClaim(ContractModel):
    """Response of POST /replays/{id}/claim."""

    replay: Replay
    bundle: ReplayBundle
