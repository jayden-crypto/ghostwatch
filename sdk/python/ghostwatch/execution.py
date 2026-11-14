"""Executions and steps: context managers that turn a run into the Ghostwatch event stream."""

from __future__ import annotations

import contextvars
import json
import threading
import traceback
import uuid
from datetime import datetime, timezone
from types import TracebackType
from typing import Any

_current_execution: contextvars.ContextVar[Execution | None] = contextvars.ContextVar(
    "ghostwatch_execution", default=None
)
_current_step: contextvars.ContextVar[Step | None] = contextvars.ContextVar("ghostwatch_step", default=None)

STEP_TYPES = ("input", "llm_call", "tool_call", "retrieval", "reasoning", "output", "custom")


def current_execution() -> Execution | None:
    return _current_execution.get()


def format_timestamp(value: datetime) -> str:
    value = value.astimezone(timezone.utc)
    return f"{value:%Y-%m-%dT%H:%M:%S}.{value.microsecond // 1000:03d}Z"


def to_json(value: Any) -> Any:
    """A JSON-safe copy of `value`. Never raises: anything unserialisable becomes its repr."""
    try:
        json.dumps(value, allow_nan=False)  # NaN and infinity are not JSON
        return value
    except (TypeError, ValueError):
        pass
    if isinstance(value, dict):
        return {str(key): to_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json(item) for item in value]
    return repr(value)


def error_info(exc: BaseException) -> dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "stacktrace": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }


class Step:
    """One recorded step. Set `output`, `tokens_input`, `tokens_output` or `metadata` inside the block."""

    def __init__(
        self,
        execution: Execution,
        name: str,
        type: str,
        *,
        input: Any = None,
        tool_name: str | None = None,
        model: str | None = None,
        attempt: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if type not in STEP_TYPES:
            raise ValueError(f"step type must be one of {STEP_TYPES}, not {type!r}")
        self.id = f"stp_{uuid.uuid4().hex}"
        self.name = name
        self.type = type
        self.input = input
        self.tool_name = tool_name
        self.model = model
        self.attempt = attempt
        self.output: Any = None
        self.tokens_input: int | None = None
        self.tokens_output: int | None = None
        self.metadata: dict[str, Any] = {}
        self._start_metadata = metadata or {}
        self._execution = execution
        self._token: contextvars.Token[Step | None] | None = None

    def __enter__(self) -> Step:
        parent = _current_step.get()
        self._token = _current_step.set(self)
        self._execution._emit(
            "step.started",
            {
                "step_id": self.id,
                "parent_step_id": parent.id if parent is not None else None,
                "name": self.name,
                "step_type": self.type,
                "input": to_json(self.input),
                "tool_name": self.tool_name,
                "model": self.model,
                "attempt": self.attempt,
                "metadata": to_json(self._start_metadata),
            },
        )
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> bool:
        if self._token is not None:
            _current_step.reset(self._token)
        if exc is None:
            self._execution._emit(
                "step.completed",
                {
                    "step_id": self.id,
                    "output": to_json(self.output),
                    "tokens_input": self.tokens_input,
                    "tokens_output": self.tokens_output,
                    "metadata": to_json(self.metadata),
                },
            )
        else:
            self._execution._emit(
                "step.failed", {"step_id": self.id, "error": error_info(exc), "output": to_json(self.output)}
            )
        return False  # never swallow the agent's exception


class Execution:
    """One run of the agent. Use `with ghostwatch.execution(...) as run:`."""

    def __init__(
        self,
        sdk: Any,
        *,
        input: Any = None,
        config: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        replay_of: str | None = None,
        replay_id: str | None = None,
    ) -> None:
        self.id: str | None = None  # assigned in the background once Ghostwatch has created it
        self.input = input
        self.config = config or {}
        self.tags = tags or []
        self.replay_of = replay_of
        self.replay_id = replay_id
        self.output: Any = None
        self._sdk = sdk
        self._seq = 0
        self._lock = threading.Lock()
        self._consecutive_failures: dict[str, int] = {}
        self._started_at: datetime | None = None
        self._token: contextvars.Token[Execution | None] | None = None

    def step(
        self,
        name: str,
        type: str = "custom",
        *,
        input: Any = None,
        tool_name: str | None = None,
        model: str | None = None,
        attempt: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> Step:
        return Step(
            self,
            name,
            type,
            input=input,
            tool_name=tool_name,
            model=model,
            attempt=attempt,
            metadata=metadata,
        )

    def log(self, message: str, level: str = "info") -> None:
        step = _current_step.get()
        self._emit("log", {"level": level, "message": str(message), "step_id": step.id if step else None})

    def create_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "input": to_json(self.input),
            "config": to_json(self.config),
            "tags": list(self.tags),
            "started_at": format_timestamp(self._started_at or self._sdk.now()),
        }
        if self.replay_of is not None:
            payload["replay_of"] = self.replay_of
        if self.replay_id is not None:
            payload["replay_id"] = self.replay_id
        return payload

    def __enter__(self) -> Execution:
        self._started_at = self._sdk.now()
        self._token = _current_execution.set(self)
        self._sdk.last_execution = self
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> bool:
        if self._token is not None:
            _current_execution.reset(self._token)
        if exc is None:
            self._emit("execution.completed", {"output": to_json(self.output)}, terminal=True)
        else:
            self._emit("execution.failed", {"error": error_info(exc)}, terminal=True)
        return False

    # -- internals -----------------------------------------------------------------------------

    def _emit(self, type: str, payload: dict[str, Any], *, terminal: bool = False) -> None:
        """Queue one event. Recording must never break the agent, so every failure is swallowed."""
        try:
            with self._lock:
                self._seq += 1
                event = {
                    "seq": self._seq,
                    "type": type,
                    "timestamp": format_timestamp(self._sdk.now()),
                    "payload": payload,
                }
                self._sdk.transport.enqueue(self, event, terminal=terminal)
        except Exception:
            self._sdk.warn_once("could not record an event; the agent continues")

    def _next_attempt(self, tool_name: str) -> int:
        """1 for a first call; n + 1 after n consecutive failed calls of the same tool in this run."""
        with self._lock:
            return self._consecutive_failures.get(tool_name, 0) + 1

    def _record_tool_result(self, tool_name: str, *, failed: bool) -> None:
        with self._lock:
            self._consecutive_failures[tool_name] = (
                self._consecutive_failures.get(tool_name, 0) + 1 if failed else 0
            )
