"""Build demo history by running the agents through the SDK against the live API.

    cd demo && uv run python seed.py            # baselines + the support-triage incidents
    cd demo && uv run python seed.py --all      # also the schema-change and ghost-invoice failures

Nothing is inserted into the database directly: every execution, step, anomaly and investigation
that appears afterwards was produced by the backend from the events these runs sent. The runs are
backdated over the last 6 days with a simulated clock, which keeps all of them inside the
dashboard's 7-day window (today plus the six days before it, in UTC).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import ghostwatch as gw

from fake_services.timing import timing
from runner import api_get, require_api, run_agent, use_agent
from scenarios import AGENTS, SCENARIOS, healthy_input

# Incidents placed in the recent past, as (scenario, minutes before now).
SUPPORT_INCIDENTS = [("rate-limit", 120), ("slow", 60)]
OTHER_INCIDENTS = [("schema-change", 30), ("ghost-invoice", 20)]


def seed(
    *, runs_per_agent: int = 25, days: int = 6, include_failures: bool = False, now: datetime | None = None
) -> int:
    """Run the history. Returns the number of executions sent."""
    now = now or datetime.now(timezone.utc)
    interval = (timedelta(days=days) - timedelta(hours=3)) / runs_per_agent
    incidents = SUPPORT_INCIDENTS + (OTHER_INCIDENTS if include_failures else [])
    sent = 0
    try:
        for agent_index, slug in enumerate(AGENTS):
            use_agent(slug, clock=timing.now)
            first_start = now - timedelta(days=days) + timedelta(minutes=7 * agent_index)
            for index in range(runs_per_agent):
                timing.use_simulated_time(first_start + index * interval)
                result = run_agent(slug, healthy_input(slug, index), seed=index)
                if result.error is not None:
                    raise SystemExit(
                        f"A healthy {slug} run failed, which should never happen: {result.error!r}"
                    )
                sent += 1
            for name, minutes_ago in incidents:
                scenario = SCENARIOS[name]
                if scenario.agent == slug:
                    timing.use_simulated_time(now - timedelta(minutes=minutes_ago))
                    run_agent(slug, scenario.input, disturb=scenario.disturb, seed=1000)
                    sent += 1
            if not gw.flush(timeout=120):
                raise SystemExit(
                    f"Ghostwatch did not accept the {slug} runs; nothing more was sent. Check its log."
                )
            print(f"  {slug}: sent")
    finally:
        timing.use_real_time()
    return sent


def print_summary() -> None:
    """What Ghostwatch now reports, read back from its API."""
    agents = api_get("/agents")["items"]
    print(f"\n{'agent':<22}{'health':<10}{'runs':>6}{'success':>9}{'open anomalies':>16}")
    for agent in agents:
        stats = agent["stats"]
        rate = "-" if stats["success_rate"] is None else f"{stats['success_rate']:.0%}"
        print(
            f"{agent['slug']:<22}{stats['health']:<10}{stats['total_executions']:>6}{rate:>9}{stats['open_anomalies']:>16}"
        )
    anomalies = api_get("/anomalies?limit=200")
    for anomaly in sorted(anomalies["items"], key=lambda item: item["detected_at"]):
        print(f"  [{anomaly['severity']}] {anomaly['type']} on {anomaly['agent_name']}: {anomaly['title']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--runs", type=int, default=25, help="healthy runs per agent (default 25)")
    parser.add_argument("--days", type=int, default=6, help="how far back the history starts (default 6)")
    parser.add_argument(
        "--all", action="store_true", help="also seed the schema-change and ghost-invoice failures"
    )
    parser.add_argument("--append", action="store_true", help="seed even if executions already exist")
    args = parser.parse_args()

    require_api()
    existing = api_get("/stats/overview?window=30d")["total_executions"]
    if existing and not args.append:
        raise SystemExit(
            f"Ghostwatch already has {existing} executions in the last 30 days. Seeding again would add a "
            "second copy of the history. Pass --append to do it anyway."
        )
    print(f"Seeding {args.runs} runs per agent over {args.days} days ...")
    sent = seed(runs_per_agent=args.runs, days=args.days, include_failures=args.all)
    print(f"Sent {sent} executions.")
    print_summary()


if __name__ == "__main__":
    main()
