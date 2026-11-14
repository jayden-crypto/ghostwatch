"""Contract §0 and §2: conventions and types shared by every schema."""

import re
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    PlainSerializer,
    PlainValidator,
    StringConstraints,
    WithJsonSchema,
)

from app.schemas.enums import EvidenceKind
from app.timeutil import format_timestamp

_CONTRACT_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")


class ContractModel(BaseModel):
    """Rejects unknown keys, so a payload that drifts from the contract fails validation.

    Response fields are declared without defaults: a nullable field must still be present.
    """

    model_config = ConfigDict(extra="forbid")


def _prefixed_id(prefix: str) -> Any:
    return Annotated[str, StringConstraints(pattern=rf"^{prefix}_[0-9a-f]{{32}}$")]


AgentId = _prefixed_id("agt")
ExecutionId = _prefixed_id("exe")
StepId = _prefixed_id("stp")
EventId = _prefixed_id("evt")
AnomalyId = _prefixed_id("anm")
InvestigationId = _prefixed_id("inv")
ReplayId = _prefixed_id("rpl")
AnyId = Annotated[str, StringConstraints(pattern=r"^(agt|exe|stp|evt|anm|inv|rpl)_[0-9a-f]{32}$")]

# Arbitrary JSON. Values come from parsed request bodies or JSONB columns, so they are JSON already.
Json = Any


def _contract_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)
    if isinstance(value, str):
        if not _CONTRACT_TIMESTAMP.fullmatch(value):
            raise ValueError("timestamp must be ISO 8601 UTC with millisecond precision and a Z suffix")
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    raise ValueError("timestamp must be an ISO 8601 string")


# Timestamp in a response: always serialised as 2026-11-14T10:32:05.123Z, and only that form validates.
Timestamp = Annotated[
    datetime,
    PlainValidator(_contract_timestamp),
    PlainSerializer(format_timestamp, return_type=str),
    WithJsonSchema({"type": "string", "format": "date-time", "examples": ["2026-11-14T10:32:05.123Z"]}),
]


def _require_string(value: Any) -> Any:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO 8601 string, not a number")
    return value


# Timestamp in a request: any ISO 8601 string with a UTC offset; converted to UTC.
InputTimestamp = Annotated[
    AwareDatetime, BeforeValidator(_require_string), AfterValidator(lambda value: value.astimezone(UTC))
]


class Page[T](ContractModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorInfo(ContractModel):
    type: str
    message: str
    stacktrace: str | None


class Evidence(ContractModel):
    kind: EvidenceKind
    label: str
    ref_id: AnyId | None
    field: str | None
    observed: Json
    expected: Json
    excerpt: str | None
