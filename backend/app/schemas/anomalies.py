"""Contract §8: Anomalies."""

from pydantic import Field

from app.schemas.common import AgentId, AnomalyId, ContractModel, Evidence, ExecutionId, Timestamp
from app.schemas.enums import AnomalyStatus, AnomalyType, Severity


class Anomaly(ContractModel):
    id: AnomalyId
    type: AnomalyType
    severity: Severity
    status: AnomalyStatus
    agent_id: AgentId
    agent_name: str
    execution_id: ExecutionId | None
    detected_at: Timestamp
    rule_id: str
    title: str = Field(max_length=80)
    explanation: str
    evidence: list[Evidence] = Field(min_length=1)
