"""Background transport: batches events and sends them without ever blocking or failing the agent.

Every network call happens on a daemon thread (or inside an explicit, time-bounded `flush`). When
Ghostwatch is unreachable the events of a run are retried a few times and then dropped with a
warning. Nothing here raises into the host program.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from typing import Any

logger = logging.getLogger("ghostwatch")

MAX_EVENTS_PER_REQUEST = 500  # API limit per batch
MAX_PENDING_PER_RUN = 10_000
MAX_ATTEMPTS = 5


class _Rejected(Exception):
    """The server understood the request and refused it (4xx): retrying cannot help."""


class _Unavailable(Exception):
    """Network failure, timeout or 5xx: worth retrying."""


class _RunState:
    def __init__(self, run: Any) -> None:
        self.run = run
        self.pending: deque[dict[str, Any]] = deque()
        self.closed = False  # the terminal event has been queued
        self.dead = False  # given up on: further events are dropped
        self.failures = 0
        self.next_attempt = 0.0


class Transport:
    def __init__(
        self,
        api_url: str,
        api_key: str,
        agent: Any,
        *,
        flush_interval: float = 0.5,
        batch_size: int = 50,
        timeout: float = 5.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.agent = agent
        self.flush_interval = flush_interval
        self.batch_size = batch_size
        self.timeout = timeout
        self._agent_id: str | None = None
        self._states: list[_RunState] = []
        self._by_run: dict[int, _RunState] = {}
        self._buffer_lock = threading.Lock()
        self._drain_lock = threading.Lock()  # one sender at a time keeps events in order
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- called from the agent's threads: must be quick and must not raise ---------------------

    def enqueue(self, run: Any, event: dict[str, Any], *, terminal: bool = False) -> None:
        with self._buffer_lock:
            state = self._by_run.get(id(run))
            if state is None:
                state = _RunState(run)
                self._by_run[id(run)] = state
                self._states.append(state)
            if state.dead:
                # Keep the state until the run ends, so its later events are still recognised and dropped.
                state.closed = state.closed or terminal
                return
            if len(state.pending) >= MAX_PENDING_PER_RUN:
                self._give_up(state, f"more than {MAX_PENDING_PER_RUN} events are waiting to be sent")
                return
            state.pending.append(event)
            state.closed = state.closed or terminal
            should_wake = terminal or len(state.pending) >= self.batch_size
        self._ensure_thread()
        if should_wake:
            self._wake.set()

    def flush(self, timeout: float = 5.0) -> bool:
        """Send everything that is waiting. Returns True if nothing is left, False on timeout or failure."""
        deadline = time.monotonic() + timeout
        if not self._drain_lock.acquire(timeout=timeout):
            return False
        try:
            self._drain(force=True, deadline=deadline)
        finally:
            self._drain_lock.release()
        return self.pending_count() == 0

    def pending_count(self) -> int:
        with self._buffer_lock:
            return sum(len(state.pending) for state in self._states)

    def close(self, timeout: float = 5.0) -> bool:
        sent = self.flush(timeout)
        self._stop.set()
        self._wake.set()
        return sent

    # -- background thread ---------------------------------------------------------------------

    def _ensure_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            with self._buffer_lock:
                if self._thread is None or not self._thread.is_alive():
                    self._thread = threading.Thread(target=self._loop, name="ghostwatch-flush", daemon=True)
                    self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self.flush_interval)
            self._wake.clear()
            try:
                with self._drain_lock:
                    self._drain(force=False, deadline=None)
            except Exception:  # the sender must survive anything
                logger.warning("Ghostwatch: unexpected error while sending events", exc_info=True)

    def _drain(self, *, force: bool, deadline: float | None) -> None:
        with self._buffer_lock:
            states = list(self._states)
        for state in states:
            if deadline is not None and time.monotonic() >= deadline:
                break
            if state.pending and not state.dead and (force or time.monotonic() >= state.next_attempt):
                self._send_run(state, deadline)
        with self._buffer_lock:
            finished = [state for state in self._states if state.closed and not state.pending]
            for state in finished:
                self._states.remove(state)
                del self._by_run[id(state.run)]

    def _send_run(self, state: _RunState, deadline: float | None) -> None:
        try:
            if state.run.id is None:
                state.run.id = self._create_execution(state.run, deadline)
            while True:
                with self._buffer_lock:
                    batch = list(state.pending)[:MAX_EVENTS_PER_REQUEST]
                if not batch:
                    break
                self._post(f"/executions/{state.run.id}/events", {"events": batch}, deadline)
                with self._buffer_lock:
                    for _ in batch:
                        state.pending.popleft()
            state.failures = 0
        except _Rejected as exc:
            with self._buffer_lock:
                self._give_up(state, str(exc))
        except _Unavailable as exc:
            state.failures += 1
            if state.failures >= MAX_ATTEMPTS:
                with self._buffer_lock:
                    self._give_up(state, f"{exc} ({MAX_ATTEMPTS} attempts)")
            else:
                state.next_attempt = time.monotonic() + 0.5 * 2 ** (state.failures - 1)
                if state.failures == 1:
                    logger.warning(
                        "Ghostwatch is unreachable (%s); the agent continues, events will be retried", exc
                    )

    def _give_up(self, state: _RunState, reason: str) -> None:
        """Caller holds the buffer lock."""
        dropped = len(state.pending)
        state.pending.clear()
        state.dead = True
        logger.warning(
            "Ghostwatch: dropped %d event(s) of a run and stopped recording it: %s", dropped, reason
        )

    def _create_execution(self, run: Any, deadline: float | None) -> str:
        if self._agent_id is None:
            self._agent_id = self._post("/agents", self.agent.to_payload(), deadline)["id"]
        return self._post("/executions", {"agent_id": self._agent_id, **run.create_payload()}, deadline)["id"]

    def _post(self, path: str, body: dict[str, Any], deadline: float | None) -> dict[str, Any]:
        timeout = self.timeout
        if deadline is not None:
            timeout = max(min(timeout, deadline - time.monotonic()), 0.1)
        request = urllib.request.Request(
            self.api_url + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = _error_message(exc)
            if exc.code >= 500 or exc.code == 429:
                raise _Unavailable(f"HTTP {exc.code} from {path}: {detail}") from None
            raise _Rejected(f"HTTP {exc.code} from {path}: {detail}") from None
        except (OSError, ValueError) as exc:  # connection refused, DNS, timeout, bad JSON
            raise _Unavailable(f"{type(exc).__name__}: {exc}") from None


def _error_message(exc: urllib.error.HTTPError) -> str:
    try:
        return json.loads(exc.read())["error"]["message"]
    except Exception:
        return exc.reason if isinstance(exc.reason, str) else "no error body"


class NullTransport:
    """Used before `init()`: the agent still runs, nothing is recorded."""

    def enqueue(self, run: Any, event: dict[str, Any], *, terminal: bool = False) -> None:
        return None

    def flush(self, timeout: float = 5.0) -> bool:
        return True

    def pending_count(self) -> int:
        return 0

    def close(self, timeout: float = 5.0) -> bool:
        return True
