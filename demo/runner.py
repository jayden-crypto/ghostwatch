"""Shared by seed.py and run_scenario.py: run an agent through the SDK and read results back from the API."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import ghostwatch as gw

import settings
from fake_services.timing import timing
from scenarios import AGENTS, reset_services


@dataclass
class RunResult:
    execution: gw.Execution
    output: dict | None
    error: Exception | None


def use_agent(slug: str, *, clock: Callable[[], datetime] | None = None) -> None:
    """Point the SDK at Ghostwatch as this agent."""
    gw.init(agent=AGENTS[slug].AGENT, api_url=settings.api_url(), api_key=settings.api_key(), clock=clock)


def run_agent(
    slug: str, input: dict, *, disturb: Callable[[], None] | None = None, seed: int = 0
) -> RunResult:
    """Run the agent once. `disturb` changes a fake service first, as an outage or an API change would."""
    reset_services()
    if disturb is not None:
        disturb()
    timing.reseed(seed)
    output, error = None, None
    try:
        output = AGENTS[slug].run(input)
    except Exception as exc:  # an agent failing is a result here, not a crash of the demo
        error = exc
    finally:
        reset_services()
    return RunResult(gw.last_execution(), output, error)


def api_get(path: str) -> dict | None:
    """GET from the Ghostwatch API. None for a 404; raises OSError if the API cannot be reached."""
    try:
        with urllib.request.urlopen(settings.api_url() + path, timeout=10) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def api_post(path: str, body: dict) -> dict:
    """POST JSON to the Ghostwatch API. Raises SystemExit with the API's own message if it refuses."""
    request = urllib.request.Request(
        settings.api_url() + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        error = json.loads(exc.read())["error"]
        raise SystemExit(f"Ghostwatch refused ({exc.code} {error['code']}): {error['message']}") from None


def require_api() -> None:
    """Stop with a clear message unless the API and its database are up."""
    try:
        health = api_get("/health")
    except OSError as exc:
        raise SystemExit(
            f"Cannot reach Ghostwatch at {settings.api_url()} ({exc}).\n"
            "Start it first: docker compose up -d && cd backend && uv run alembic upgrade head "
            "&& uv run uvicorn app.main:app"
        ) from None
    if health is None or health.get("database") != "ok":
        raise SystemExit("Ghostwatch is running but its database is not reachable (see /health).")
