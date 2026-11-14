"""Which schema each file in contract/fixtures/ must validate against.

Fixtures are named `<resource>.<operation>[.<variant>].json`. The (resource, operation) pair picks
the schema; the variant is free text. A fixture that matches nothing here fails the conformance
suite on purpose: either add its operation below or rename the fixture.
"""

from typing import Any

from pydantic import TypeAdapter

from app.schemas.agents import Agent
from app.schemas.anomalies import Anomaly
from app.schemas.common import ErrorEnvelope, Page
from app.schemas.events import IngestResponse, StoredEvent
from app.schemas.executions import ExecutionDetail, ExecutionSummary
from app.schemas.health import Health
from app.schemas.investigations import Investigation
from app.schemas.replays import Replay, ReplayClaim
from app.schemas.stats import StatsOverview, StatsTimeseries
from app.schemas.traces import Trace

SCHEMAS: dict[tuple[str, str], Any] = {
    ("agents", "list"): Page[Agent],
    ("agents", "get"): Agent,
    ("agents", "create"): Agent,
    ("executions", "list"): Page[ExecutionSummary],
    ("executions", "get"): ExecutionDetail,
    ("executions", "create"): ExecutionDetail,
    ("executions", "trace"): Trace,
    ("executions", "events"): Page[StoredEvent],
    ("executions", "ingest"): IngestResponse,
    ("executions", "replay"): Replay,
    ("events", "list"): Page[StoredEvent],
    ("events", "ingest"): IngestResponse,
    ("stats", "overview"): StatsOverview,
    ("stats", "timeseries"): StatsTimeseries,
    ("anomalies", "list"): Page[Anomaly],
    ("anomalies", "get"): Anomaly,
    ("anomalies", "update"): Anomaly,
    ("investigations", "list"): Page[Investigation],
    ("investigations", "get"): Investigation,
    ("investigations", "create"): Investigation,
    ("replays", "list"): Page[Replay],
    ("replays", "get"): Replay,
    ("replays", "create"): Replay,
    ("replays", "claim"): ReplayClaim,
    ("health", "get"): Health,
}


def schema_for(filename: str) -> TypeAdapter[Any] | None:
    """The validator for a fixture file name, or None when nothing is mapped to it."""
    parts = filename.removesuffix(".json").split(".")
    if parts[0] == "error":
        return TypeAdapter(ErrorEnvelope)
    if len(parts) < 2 or (parts[0], parts[1]) not in SCHEMAS:
        return None
    return TypeAdapter(SCHEMAS[(parts[0], parts[1])])
