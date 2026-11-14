"""Ghostwatch SDK.

    import ghostwatch as gw

    gw.init(agent=gw.Agent(slug="research-assistant", name="Research Assistant"))

    @gw.tool
    def web_search(query: str) -> dict: ...

    with gw.execution(input={"question": q}) as run:
        with run.step("plan", type="reasoning") as step:
            step.output = {"queries": [q]}
        results = web_search(q)          # recorded as a tool_call step
        run.output = {"answer": ...}

Recording is fail-open: if Ghostwatch is down, slow or misconfigured, the agent runs exactly as it
would without the SDK. Exceptions raised by the agent are recorded and then re-raised unchanged.
"""

from __future__ import annotations

import atexit
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ghostwatch.client import NullTransport, Transport
from ghostwatch.execution import Execution, Step, current_execution
from ghostwatch.tools import llm_call, tool

__all__ = [
    "Agent",
    "Execution",
    "Step",
    "current_execution",
    "execution",
    "flush",
    "init",
    "last_execution",
    "llm_call",
    "tool",
]
__version__ = "0.1.0"

logger = logging.getLogger("ghostwatch")


@dataclass
class Agent:
    slug: str
    name: str
    description: str | None = None
    framework: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "framework": self.framework,
            "metadata": self.metadata,
        }


class _Sdk:
    def __init__(self) -> None:
        self.transport: Any = NullTransport()
        self.clock: Callable[[], datetime] | None = None
        self.initialised = False
        self.last_execution: Execution | None = None
        self._warned: set[str] = set()
        self._lock = threading.Lock()

    def now(self) -> datetime:
        return self.clock() if self.clock is not None else datetime.now(timezone.utc)

    def warn_once(self, message: str) -> None:
        with self._lock:
            if message in self._warned:
                return
            self._warned.add(message)
        logger.warning("Ghostwatch: %s", message)


_sdk = _Sdk()
_atexit_registered = False


def init(
    *,
    agent: Agent,
    api_url: str | None = None,
    api_key: str | None = None,
    flush_interval: float = 0.5,
    batch_size: int = 50,
    timeout: float = 5.0,
    clock: Callable[[], datetime] | None = None,
) -> None:
    """Configure the SDK. Makes no network call: the agent is registered when its first run is sent.

    `api_url` and `api_key` default to the GHOSTWATCH_API_URL and GHOSTWATCH_API_KEY environment
    variables. `clock` replaces the wall clock for event timestamps (used to seed backdated history).
    """
    global _atexit_registered
    api_url = api_url or os.environ.get("GHOSTWATCH_API_URL", "http://localhost:8000/api/v1")
    api_key = api_key or os.environ.get("GHOSTWATCH_API_KEY", "")
    _sdk.transport.close()
    _sdk.transport = Transport(
        api_url, api_key, agent, flush_interval=flush_interval, batch_size=batch_size, timeout=timeout
    )
    _sdk.clock = clock
    _sdk.initialised = True
    if not api_key:
        _sdk.warn_once("no API key configured (GHOSTWATCH_API_KEY); Ghostwatch will reject the events")
    if not _atexit_registered:
        atexit.register(_flush_at_exit)
        _atexit_registered = True


def execution(
    *,
    input: Any = None,
    config: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    replay_of: str | None = None,
    replay_id: str | None = None,
) -> Execution:
    """Start recording one run: `with ghostwatch.execution(input=...) as run:`."""
    if not _sdk.initialised:
        _sdk.warn_once("execution() used before init(); the agent runs normally but nothing is recorded")
    return Execution(_sdk, input=input, config=config, tags=tags, replay_of=replay_of, replay_id=replay_id)


def last_execution() -> Execution | None:
    """The execution most recently entered in this process (its `id` is set once it has been sent)."""
    return _sdk.last_execution


def flush(timeout: float = 5.0) -> bool:
    """Send everything recorded so far, waiting at most `timeout` seconds. True if nothing is left."""
    try:
        return _sdk.transport.flush(timeout)
    except Exception:
        _sdk.warn_once("flush failed; the agent continues")
        return False


def _flush_at_exit() -> None:
    if not flush(timeout=5.0):
        logger.warning(
            "Ghostwatch: %d event(s) could not be sent before exit", _sdk.transport.pending_count()
        )
