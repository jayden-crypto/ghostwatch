"""Replaying a recorded execution: what is served from the recording, what runs, and what is blocked.

Sandbox rule (API contract §10):
- A tool or LLM call the original execution recorded returns its recorded output (or raises its
  recorded error). The function is not called.
- A call the original never made runs for real only if it is an LLM call or a tool declared
  `side_effects=False`. Any other tool is never called; its step fails with SandboxRecordingMissing.
  A tool that does not declare `side_effects` counts as having them.

Every step of a replay carries `metadata.replay_source`: "recorded", "executed" or "blocked".

The sandbox controls calls made through `@ghostwatch.tool` and `@ghostwatch.llm_call`. Anything an
agent does outside those decorators runs as ordinary code in every mode, so side effects belong
inside a decorated tool.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import contextvars
import inspect
import threading
from collections import defaultdict
from collections.abc import Callable, Iterator
from typing import Any

RECORDED = "recorded"
EXECUTED = "executed"
BLOCKED = "blocked"


class SandboxRecordingMissing(Exception):
    """A sandbox replay reached a tool call it may not run and has no recording for."""


class RecordedCallError(Exception):
    """A recorded failure whose original exception class could not be found in the agent's code."""


class ReplayNotPossible(Exception):
    """The replay cannot be run faithfully, so it is failed with this error instead of guessed at."""


def _is_truncated(value: Any) -> bool:
    return isinstance(value, dict) and value.get("_truncated") is True


class ReplaySession:
    """One claimed replay: its mode and the original execution's recorded calls."""

    def __init__(self, claim: dict[str, Any]) -> None:
        replay, bundle = claim["replay"], claim["bundle"]
        self.replay_id: str = replay["id"]
        self.mode: str = replay["mode"]
        self.side_effects_authorized: bool = replay["side_effects_authorized"]
        self.original: dict[str, Any] = bundle["original_execution"]
        self.started = False  # set when an execution has been opened for this replay
        self._lock = threading.Lock()
        self._next: dict[tuple[str, str], int] = defaultdict(int)
        self._recordings: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for call in sorted(bundle["recorded_calls"], key=lambda call: call["occurrence"]):
            self._recordings[(call["step_type"], call["tool_name"] or call["step_name"])].append(call)

    def problem(self) -> str | None:
        """Why this replay must not be run at all, or None."""
        if self.mode == "live" and not self.side_effects_authorized:
            return "a live replay needs side-effect authorization, and this one does not have it"
        if _is_truncated(self.original["input"]):
            return "the original input was larger than 64 KB and only a preview of it was stored"
        return None

    def resolve(
        self, step_type: str, name: str, *, safe: bool
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        """Decide how the next call of `name` is handled: (replay_source, recording, why blocked).

        `safe` is True for an LLM call and for a tool declared `side_effects=False`.
        """
        if self.mode == "live":
            return EXECUTED, None, None
        key = (step_type, name)
        with self._lock:
            index = self._next[key]
            self._next[key] += 1
        recordings = self._recordings.get(key, [])
        if index < len(recordings):
            recording = recordings[index]
            if recording["error"] is None and _is_truncated(recording["output"]):
                reason = (
                    f"the recorded output of {name} (call {index + 1}) was larger than 64 KB and only a "
                    "preview of it was stored, so it cannot be served"
                )
                return BLOCKED, None, reason
            return RECORDED, recording, None
        if safe:
            return EXECUTED, None, None
        reason = (
            f"{name} has no recording for call {index + 1} (the original execution made {len(recordings)}) "
            "and is not declared side_effects=False, so it is not run in a sandbox replay"
        )
        return BLOCKED, None, reason


def recorded_exception(error: dict[str, Any], function: Callable[..., Any]) -> BaseException:
    """Rebuild the exception a recorded call raised, as the same class when the agent's code has it.

    The class is looked up by name where the decorated function lives and among the builtins, so an
    agent's own `except RateLimited:` still catches it. If it cannot be found, the error is raised
    as a RecordedCallError subclass carrying the original class name.
    """
    name, message = error["type"], error["message"]
    # Unwrapped first: a decorated function's own globals are the decorator's module, not the agent's.
    module_names = getattr(inspect.unwrap(function), "__globals__", {})
    found = module_names.get(name) or getattr(builtins, name, None)
    if isinstance(found, type) and issubclass(found, Exception):
        argument: Any = message
        if issubclass(found, KeyError):
            # str(KeyError("results")) is "'results'": undo that so the key is not quoted twice.
            with contextlib.suppress(ValueError, SyntaxError):
                argument = ast.literal_eval(message)
        with contextlib.suppress(Exception):
            return found(argument)
    return type(name, (RecordedCallError,), {})(message)


_pending: contextvars.ContextVar[ReplaySession | None] = contextvars.ContextVar(
    "ghostwatch_replay", default=None
)


@contextlib.contextmanager
def replaying(session: ReplaySession) -> Iterator[ReplaySession]:
    """The first execution opened inside this block is the run of `session`'s replay."""
    token = _pending.set(session)
    try:
        yield session
    finally:
        _pending.reset(token)


def take_pending() -> ReplaySession | None:
    """The replay session waiting for an execution, if any. Each session is handed out once."""
    session = _pending.get()
    if session is None or session.started:
        return None
    session.started = True
    return session
