"""Builders for ingestion request bodies, as an SDK would send them."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from httpx2 import Response

from app import ids
from app.timeutil import format_timestamp
from tests.factories import T0

KEY_ERROR = {
    "type": "KeyError",
    "message": "'results'",
    "stacktrace": "Traceback (most recent call last): ...",
}


def at(offset_ms: int) -> str:
    """A contract timestamp `offset_ms` after T0 (the default execution start in the factories)."""
    return format_timestamp(T0 + timedelta(milliseconds=offset_ms))


def new_step_id() -> str:
    return ids.new_id(ids.STEP)


def _event(seq: int, type_: str, offset_ms: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {"seq": seq, "type": type_, "timestamp": at(offset_ms), "payload": payload}


def step_started(
    seq: int,
    step_id: str,
    offset_ms: int = 0,
    *,
    name: str = "plan",
    step_type: str = "reasoning",
    **payload: Any,
) -> dict[str, Any]:
    return _event(
        seq, "step.started", offset_ms, {"step_id": step_id, "name": name, "step_type": step_type, **payload}
    )


def step_completed(seq: int, step_id: str, offset_ms: int = 0, **payload: Any) -> dict[str, Any]:
    return _event(seq, "step.completed", offset_ms, {"step_id": step_id, **payload})


def step_failed(
    seq: int, step_id: str, offset_ms: int = 0, *, error: dict | None = None, **payload: Any
) -> dict[str, Any]:
    return _event(seq, "step.failed", offset_ms, {"step_id": step_id, "error": error or KEY_ERROR, **payload})


def execution_completed(seq: int, offset_ms: int = 0, **payload: Any) -> dict[str, Any]:
    return _event(seq, "execution.completed", offset_ms, payload)


def execution_failed(seq: int, offset_ms: int = 0, *, error: dict | None = None) -> dict[str, Any]:
    return _event(seq, "execution.failed", offset_ms, {"error": error or KEY_ERROR})


def execution_timed_out(seq: int, offset_ms: int = 0) -> dict[str, Any]:
    return _event(seq, "execution.timed_out", offset_ms, {})


def log(
    seq: int, offset_ms: int = 0, *, message: str = "hello", level: str = "info", **payload: Any
) -> dict[str, Any]:
    return _event(seq, "log", offset_ms, {"level": level, "message": message, **payload})


def post_events(
    client: TestClient, auth: dict[str, str], execution_id: str, events: list[dict[str, Any]]
) -> Response:
    return client.post(f"/api/v1/executions/{execution_id}/events", json={"events": events}, headers=auth)
