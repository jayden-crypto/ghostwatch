"""Replay recorded runs with the demo agents' code.

A replay is requested in Ghostwatch (the dashboard's Replay button, or `request` below) and run by a
worker, because only the worker has the agent's code. Start a worker in one terminal:

cd demo && uv run python replay.py worker            # the agents exactly as they shipped
cd demo && uv run python replay.py worker --fixed    # with the parse_results fix deployed

and ask for a sandbox replay of an execution in another:

cd demo && uv run python replay.py request <execution_id>

`request` asks for sandbox replays only. A live replay runs every tool for real, so it has to be
asked for through the API with `authorize_side_effects: true`.
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable

import ghostwatch as gw

import settings
from agents import research_assistant
from runner import api_get, api_post, require_api
from scenarios import AGENTS, reset_services

SOURCES = {
    "recorded": "recorded (served from the original run, not called)",
    "executed": "executed (ran for real in this replay)",
    "blocked": "blocked (not recorded and not safe to run)",
}


def _handler(slug: str) -> Callable[[dict], dict]:
    def run(input: dict) -> dict:
        reset_services()  # the fake services behave normally; the sandbox decides which calls reach them
        return AGENTS[slug].run(input)

    return run


def build_worker(*, fixed: bool) -> gw.ReplayWorker:
    """A worker that can replay all three demo agents. `fixed` deploys the parse_results fix."""
    research_assistant.PARSER_FIX_DEPLOYED = fixed
    worker = gw.ReplayWorker(api_url=settings.api_url(), api_key=settings.api_key())
    for slug, module in AGENTS.items():
        worker.register(module.AGENT, _handler(slug))
    return worker


def request(execution_id: str, timeout: float = 60.0) -> dict:
    """Ask for a sandbox replay of the execution and wait until a worker has run it."""
    replay = api_post(f"/executions/{execution_id}/replay", {"mode": "sandbox"})
    print(f"Replay       : {replay['id']} ({replay['mode']}) of {execution_id}, waiting for a worker")
    deadline = time.monotonic() + timeout
    while replay["status"] in ("pending", "claimed") and time.monotonic() < deadline:
        time.sleep(0.25)
        replay = api_get(f"/replays/{replay['id']}")
    return replay


def _summary(execution: dict) -> str:
    error = (
        f"  <- {execution['error']['type']}: {execution['error']['message']}" if execution["error"] else ""
    )
    return f"{execution['status']} in {execution['duration_ms']} ms, {execution['step_count']} steps{error}"


def report(replay: dict) -> None:
    """Print the comparison Ghostwatch computed, read back from the API."""
    if replay["status"] == "pending":
        print("  status     : still pending. Is a worker running? (uv run python replay.py worker)")
        return
    if replay["comparison"] is None:
        print(f"  status     : {replay['status']}, no comparison yet")
        return
    comparison = replay["comparison"]
    print(f"  status     : {replay['status']}")
    print(f"  outcome    : {comparison['outcome']}")
    print(f"  original   : {_summary(comparison['original'])}")
    print(f"  replay     : {_summary(comparison['replay'])}")
    print("  steps      :")
    for diff in comparison["step_diffs"]:
        statuses = f"{diff['original_status'] or '-'} -> {diff['replay_status'] or '-'}"
        source = SOURCES.get(diff["replay_source"], "-")
        print(f"   {diff['ordinal']:>2}. {diff['name']:<14} {diff['change']:<15} {statuses:<23} {source}")
    print(f"\nOpen in the dashboard: {settings.dashboard_url()}/executions/{replay['replay_execution_id']}")


def main(argv: list[str]) -> None:
    command, arguments = (argv[0], argv[1:]) if argv else ("help", [])
    if command == "worker" and set(arguments) <= {"--fixed"}:
        require_api()
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        fixed = "--fixed" in arguments
        print(f"parse_results fix deployed: {'yes' if fixed else 'no'}. Ctrl-C to stop.")
        try:
            build_worker(fixed=fixed).run_forever()
        except KeyboardInterrupt:
            print()
    elif command == "request" and len(arguments) == 1:
        require_api()
        report(request(arguments[0]))
    else:
        print(__doc__)
        raise SystemExit(0 if command == "help" else 2)


if __name__ == "__main__":
    main(sys.argv[1:])
