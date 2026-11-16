"""Contract §7: Stats."""

from typing import Literal

from app.schemas.common import ContractModel, Timestamp

Window = Literal["24h", "7d", "30d"]
Bucket = Literal["hour", "day"]


class StatsOverview(ContractModel):
    window: Window
    total_agents: int
    total_executions: int
    completed: int
    failed: int
    timed_out: int
    running: int
    success_rate: float | None
    avg_duration_ms: int | None
    open_anomalies: int


class TimeseriesPoint(ContractModel):
    bucket_start: Timestamp
    completed: int
    failed: int
    timed_out: int
    avg_duration_ms: int | None


class StatsTimeseries(ContractModel):
    window: Window
    bucket: Bucket
    points: list[TimeseriesPoint]
