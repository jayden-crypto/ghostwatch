"""A stub Ghostwatch API on localhost, and a fixture that resets the SDK between tests."""

from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

import ghostwatch as gw
from ghostwatch.client import NullTransport

API_KEY = "stub-key"


class StubApi:
    """Records every request. `fail_next(n, status)` makes the next n event posts fail."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any], str | None]] = []
        self.replays: dict[str, dict[str, Any]] = {}  # replay id -> {"claim", "agent_slug", "status"}
        self._failures: list[int] = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/api/v1"

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def add_replay(self, claim: dict[str, Any], agent_slug: str, status: str = "pending") -> None:
        """A replay request waiting for a worker, with the claim response it will be given."""
        self.replays[claim["replay"]["id"]] = {"claim": claim, "agent_slug": agent_slug, "status": status}

    def _read(self, path: str) -> tuple[int, dict[str, Any]]:
        with self._lock:
            if path.startswith("/replays?"):
                pending = [r["claim"]["replay"] for r in self.replays.values() if r["status"] == "pending"]
                return 200, {"items": pending, "total": len(pending), "limit": 50, "offset": 0}
            for replay in self.replays.values():
                original = replay["claim"]["bundle"]["original_execution"]
                if path == f"/executions/{original['id']}":
                    return 200, original
                if path == f"/agents/{original['agent_id']}":
                    return 200, {"id": original["agent_id"], "slug": replay["agent_slug"]}
            return 404, {"error": {"code": "not_found", "message": path, "details": None}}

    def fail_next(self, count: int, status: int) -> None:
        with self._lock:
            self._failures += [status] * count

    def posts(self, suffix: str) -> list[dict[str, Any]]:
        with self._lock:
            return [body for path, body, _ in self.requests if path.endswith(suffix)]

    def events(self) -> list[dict[str, Any]]:
        """Every event from every successful batch, in arrival order."""
        with self._lock:
            return [
                event
                for path, body, _ in self.requests
                if path.endswith("/events")
                for event in body["events"]
            ]

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        api = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self._send(*api._read(self.path.removeprefix("/api/v1")))

            def do_POST(self) -> None:
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                body = json.loads(raw) if raw else {}
                path = self.path.removeprefix("/api/v1")
                self._send(*api._respond(path, body, self.headers.get("Authorization")))

            def _send(self, status: int, response: dict[str, Any]) -> None:
                payload = json.dumps(response).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: Any) -> None:
                pass

        return Handler

    def _respond(
        self, path: str, body: dict[str, Any], authorization: str | None
    ) -> tuple[int, dict[str, Any]]:
        with self._lock:
            if authorization != f"Bearer {API_KEY}":
                return 401, {
                    "error": {
                        "code": "unauthorized",
                        "message": "Missing or invalid API key.",
                        "details": None,
                    }
                }
            if path.endswith("/events") and self._failures:
                status = self._failures.pop(0)
                return status, {
                    "error": {"code": "stub", "message": f"stub failure {status}", "details": None}
                }
            self.requests.append((path, body, authorization))
            if path.startswith("/replays/") and path.endswith("/claim"):
                replay = self.replays.get(path.split("/")[2])
                if replay is None or replay["status"] != "pending":
                    return 409, {"error": {"code": "conflict", "message": "already claimed", "details": None}}
                replay["status"] = "claimed"
                return 200, replay["claim"]
            if path == "/agents":
                return 201, {"id": "agt_" + "a" * 32}
            if path == "/executions":
                return 201, {"id": f"exe_{uuid.uuid4().hex}"}
            return 202, {"accepted": len(body["events"]), "duplicates": 0, "execution_status": "running"}


def wait_for(predicate: Callable[[], bool], timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def closed_port_url() -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}/api/v1"


AGENT = gw.Agent(slug="research-assistant", name="Research Assistant", framework="custom")


@pytest.fixture
def api() -> Iterator[StubApi]:
    stub = StubApi()
    yield stub
    stub.stop()


@pytest.fixture(autouse=True)
def reset_sdk() -> Iterator[None]:
    yield
    gw._sdk.transport.close(timeout=0.2)
    gw._sdk.transport = NullTransport()
    gw._sdk.clock = None
    gw._sdk.initialised = False
    gw._sdk.last_execution = None
    gw._sdk._warned.clear()


@pytest.fixture
def sdk(api: StubApi) -> StubApi:
    """The SDK initialised against the stub, sending only on explicit flush."""
    gw.init(agent=AGENT, api_url=api.url, api_key=API_KEY, flush_interval=60, batch_size=10_000, timeout=2)
    return api
