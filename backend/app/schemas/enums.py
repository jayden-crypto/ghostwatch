"""Contract §1: enums, as exact string values."""

from typing import Literal, get_args

ExecutionStatus = Literal["running", "completed", "failed", "timed_out"]
StepStatus = Literal["running", "completed", "failed"]
StepType = Literal["input", "llm_call", "tool_call", "retrieval", "reasoning", "output", "custom"]
Severity = Literal["low", "medium", "high", "critical"]
AnomalyType = Literal[
    "duration_spike",
    "token_spike",
    "repeated_tool_failure",
    "excessive_retries",
    "repeated_timeouts",
    "ghost_completion",
    "stale_execution",
    "unexpected_pattern",
]
AnomalyStatus = Literal["open", "acknowledged", "resolved"]
AgentHealth = Literal["healthy", "degraded", "failing", "idle"]
InvestigationStatus = Literal["queued", "running", "completed", "failed"]
InvestigationTrigger = Literal["manual", "auto_failure", "auto_anomaly"]
InvestigationProvider = Literal["fable", "rule_based"]
Confidence = Literal["low", "medium", "high"]
RootCauseStatus = Literal["confirmed", "probable", "insufficient_evidence"]
EvidenceKind = Literal["step", "event", "metric", "baseline", "execution", "anomaly"]
ReplayMode = Literal["sandbox", "live"]
ReplayStatus = Literal["pending", "claimed", "completed", "failed"]
ReplayOutcome = Literal[
    "same_failure", "different_failure", "fixed", "regressed", "both_succeeded", "inconclusive"
]
StepChange = Literal["unchanged", "status_changed", "output_changed", "added", "removed"]
ReplaySource = Literal["recorded", "executed", "blocked"]
EventType = Literal[
    "step.started",
    "step.completed",
    "step.failed",
    "execution.completed",
    "execution.failed",
    "execution.timed_out",
    "log",
]

EXECUTION_STATUSES: tuple[str, ...] = get_args(ExecutionStatus)
TERMINAL_STATUSES: tuple[str, ...] = ("completed", "failed", "timed_out")
AGENT_HEALTHS: tuple[str, ...] = get_args(AgentHealth)
