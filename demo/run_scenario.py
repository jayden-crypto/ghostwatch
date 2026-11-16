"""Run one demo step live and show what Ghostwatch recorded.

cd demo && uv run python run_scenario.py healthy research-assistant
cd demo && uv run python run_scenario.py schema-change
cd demo && uv run python run_scenario.py ghost-invoice
cd demo && uv run python run_scenario.py rate-limit
cd demo && uv run python run_scenario.py slow
cd demo && uv run python run_scenario.py list
"""

from __future__ import annotations

import sys
import time

import ghostwatch as gw

import settings
from runner import RunResult, api_get, require_api, run_agent, use_agent
from scenarios import AGENTS, SCENARIOS, healthy_input


def run(name: str, agent: str | None = None) -> RunResult:
    """Run a scenario (or a healthy run of `agent`) and make sure Ghostwatch has received it."""
    if name == "healthy":
        use_agent(agent)
        result = run_agent(agent, healthy_input(agent, 0))
    else:
        scenario = SCENARIOS[name]
        use_agent(scenario.agent)
        result = run_agent(scenario.agent, scenario.input, disturb=scenario.disturb)
    if not gw.flush(timeout=15):
        raise SystemExit(
            "The agent ran, but Ghostwatch did not receive the run (unreachable or it rejected the events). "
            "Nothing was recorded."
        )
    return result


def wait_for_investigation(execution_id: str, timeout: float = 20.0) -> dict | None:
    """The investigation Ghostwatch started for this execution, once finished; None if there is none."""
    deadline = time.monotonic() + timeout
    investigation = api_get(f"/investigations/{execution_id}")
    while (
        investigation is not None
        and investigation["status"] in ("queued", "running")
        and time.monotonic() < deadline
    ):
        time.sleep(0.25)
        investigation = api_get(f"/investigations/{execution_id}")
    return investigation


def report(result: RunResult) -> None:
    """Print what the agent said happened, then what Ghostwatch recorded, read back from the API."""
    execution_id = result.execution.id
    if result.error is None:
        print(f"Agent result : returned {result.output}")
    else:
        print(f"Agent result : raised {type(result.error).__name__}: {result.error}")

    trace = api_get(f"/executions/{execution_id}/trace")
    execution = trace["execution"]
    print(f"\nGhostwatch   : execution {execution_id}")
    summary = f"{execution['status']} in {execution['duration_ms']} ms, {execution['step_count']} steps"
    print(f"  status     : {summary}")
    for step in trace["steps"]:
        attempt = f" (attempt {step['attempt']})" if step["attempt"] > 1 else ""
        error = f"  <- {step['error']['type']}: {step['error']['message']}" if step["error"] else ""
        indent = "  " * step["depth"]
        outcome = f"{step['status']}, {step['duration_ms']} ms"
        print(f"  {step['ordinal']:>2}. {indent}{step['name']}{attempt}: {outcome}{error}")
    if trace["anomalies"]:
        for anomaly in trace["anomalies"]:
            print(f"  anomaly    : [{anomaly['severity']}] {anomaly['type']}: {anomaly['title']}")
            print(f"               {anomaly['explanation']}")
    else:
        print("  anomalies  : none")

    investigation = wait_for_investigation(execution_id)
    if investigation is None:
        print("  investigation: none")
    elif investigation["status"] != "completed":
        print(f"  investigation: {investigation['status']}")
    else:
        root_cause = investigation["report"]["root_cause"]
        signature = f" (signature {root_cause['signature']})" if root_cause["signature"] else ""
        print(f"  investigation: {root_cause['status']}{signature}, provider {investigation['provider']}")
        print(f"               {root_cause['statement']}")
    print(f"\nOpen in the dashboard: {settings.dashboard_url()}/executions/{execution_id}")


def main(argv: list[str]) -> None:
    name = argv[0] if argv else "list"
    agent = argv[1] if len(argv) > 1 else None
    known = name in SCENARIOS or (name == "healthy" and agent in AGENTS)
    if name == "list" or not known:
        print(__doc__)
        print("Scenarios:")
        print(f"  {'healthy <agent>':<16} a normal run of {', '.join(AGENTS)}")
        for scenario in SCENARIOS.values():
            print(f"  {scenario.name:<16} {scenario.description}")
        raise SystemExit(0 if name == "list" else 2)

    require_api()
    description = f"a normal run of {agent}" if name == "healthy" else SCENARIOS[name].description
    print(f"Scenario     : {name} - {description}")
    report(run(name, agent))


if __name__ == "__main__":
    main(sys.argv[1:])
