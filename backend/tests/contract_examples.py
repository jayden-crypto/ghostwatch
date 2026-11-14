"""One valid JSON example of every response type in the contract, built from the schemas' own field
lists so the conformance tests can mutate them."""

from typing import Any

from app.schemas.agents import Agent
from app.schemas.anomalies import Anomaly
from app.schemas.common import ErrorEnvelope, Page
from app.schemas.events import IngestResponse, StoredEvent
from app.schemas.executions import ExecutionDetail, ExecutionSummary
from app.schemas.health import Health
from app.schemas.investigations import Investigation
from app.schemas.replays import Replay, ReplayClaim
from app.schemas.stats import StatsOverview, StatsTimeseries
from app.schemas.traces import Trace


def _id(prefix: str, number: int) -> str:
    return f"{prefix}_{number:032x}"


AGENT_ID, EXECUTION_ID, REPLAY_EXECUTION_ID = _id("agt", 1), _id("exe", 1), _id("exe", 2)
STEP_ID, EVENT_ID, ANOMALY_ID, INVESTIGATION_ID, REPLAY_ID = (
    _id("stp", 1), _id("evt", 1), _id("anm", 1), _id("inv", 1), _id("rpl", 1),
)  # fmt: skip
T1, T2 = "2026-11-14T10:32:05.123Z", "2026-11-14T10:32:07.623Z"
ERROR = {"type": "KeyError", "message": "'results'", "stacktrace": None}

EVIDENCE = {
    "kind": "step",
    "label": "Error raised by parse_results",
    "ref_id": STEP_ID,
    "field": "error.message",
    "observed": "'results'",
    "expected": None,
    "excerpt": "KeyError: 'results'",
}
SUMMARY = {
    "id": EXECUTION_ID,
    "agent_id": AGENT_ID,
    "agent_name": "Research Assistant",
    "status": "failed",
    "started_at": T1,
    "ended_at": T2,
    "duration_ms": 2500,
    "step_count": 1,
    "tokens_total": 1500,
    "cost_usd": 0.0123,
    "anomaly_count": 1,
    "has_investigation": True,
    "replay_of": None,
    "error": ERROR,
}
DETAIL = {
    **SUMMARY,
    "input": {"question": "q"},
    "output": None,
    "config": {
        "model": "claude-fable-5-2",
        "params": {},
        "expected_steps": ["web_search"],
        "timeout_ms": None,
    },
    "tokens_input": 1200,
    "tokens_output": 300,
    "tags": ["demo"],
    "replay_ids": [REPLAY_ID],
}
AGENT = {
    "id": AGENT_ID,
    "name": "Research Assistant",
    "slug": "research-assistant",
    "description": None,
    "framework": "custom",
    "metadata": {},
    "created_at": T1,
    "stats": {
        "total_executions": 1,
        "completed": 0,
        "failed": 1,
        "timed_out": 0,
        "running": 0,
        "success_rate": 0.0,
        "avg_duration_ms": 2500,
        "open_anomalies": 1,
        "last_execution": SUMMARY,
        "health": "failing",
    },
}
STEP = {
    "id": STEP_ID,
    "execution_id": EXECUTION_ID,
    "parent_step_id": None,
    "ordinal": 1,
    "depth": 0,
    "name": "parse_results",
    "type": "reasoning",
    "status": "failed",
    "started_at": T1,
    "ended_at": T2,
    "duration_ms": 2500,
    "offset_ms": 0,
    "input": None,
    "output": None,
    "error": ERROR,
    "tool_name": None,
    "model": None,
    "tokens_input": None,
    "tokens_output": None,
    "attempt": 1,
    "metadata": {},
}
ANOMALY = {
    "id": ANOMALY_ID,
    "type": "ghost_completion",
    "severity": "critical",
    "status": "open",
    "agent_id": AGENT_ID,
    "agent_name": "Research Assistant",
    "execution_id": EXECUTION_ID,
    "detected_at": T2,
    "rule_id": "ghost_completion.v1",
    "title": "Completed without submit_invoice",
    "explanation": "Status is completed but expected step submit_invoice never completed.",
    "evidence": [EVIDENCE],
}
TRACE = {"execution": DETAIL, "steps": [STEP], "anomalies": [ANOMALY], "event_count": 3}
STORED_EVENT = {
    "id": EVENT_ID,
    "seq": 1,
    "type": "execution.failed",
    "timestamp": T2,
    "received_at": T2,
    "payload": {"error": ERROR},
}
REPORT = {
    "summary": "parse_results failed because the search tool's output had no 'results' key.",
    "failing_step_id": STEP_ID,
    "root_cause": {
        "status": "confirmed",
        "statement": "Upstream output lacks the key the step read.",
        "hypothesis_id": "H1",
        "signature": "missing_key_in_upstream_output",
    },
    "facts": [
        {
            "id": "F1",
            "statement": "Step 1 parse_results failed with KeyError: 'results'.",
            "evidence": [EVIDENCE],
        }
    ],
    "hypotheses": [
        {
            "id": "H1",
            "statement": "The search API changed its response shape.",
            "confidence": "high",
            "reasoning": "F1 shows the missing key.",
            "supporting_fact_ids": ["F1"],
            "contradicting_fact_ids": [],
        }
    ],
    "recommendations": [
        {
            "id": "R1",
            "action": "Accept both shapes.",
            "rationale": "Removes the failure.",
            "hypothesis_id": "H1",
        }
    ],
    "evidence_gaps": [],
    "relevant_step_ids": [STEP_ID],
}
INVESTIGATION = {
    "id": INVESTIGATION_ID,
    "execution_id": EXECUTION_ID,
    "status": "completed",
    "trigger": "auto_failure",
    "provider": "rule_based",
    "model": None,
    "created_at": T2,
    "completed_at": T2,
    "error": None,
    "report": REPORT,
}
REPLAY_SUMMARY = {
    **SUMMARY,
    "id": REPLAY_EXECUTION_ID,
    "status": "completed",
    "error": None,
    "replay_of": EXECUTION_ID,
}
REPLAY = {
    "id": REPLAY_ID,
    "original_execution_id": EXECUTION_ID,
    "replay_execution_id": REPLAY_EXECUTION_ID,
    "mode": "sandbox",
    "status": "completed",
    "side_effects_authorized": False,
    "note": None,
    "requested_at": T1,
    "claimed_at": T1,
    "completed_at": T2,
    "error": None,
    "comparison": {
        "original": SUMMARY,
        "replay": REPLAY_SUMMARY,
        "outcome": "fixed",
        "duration_delta_ms": -500,
        "tokens_delta": None,
        "step_count_delta": 0,
        "step_diffs": [
            {
                "ordinal": 1,
                "name": "parse_results",
                "original_step_id": STEP_ID,
                "replay_step_id": _id("stp", 2),
                "change": "status_changed",
                "original_status": "failed",
                "replay_status": "completed",
            }
        ],
    },
}
REPLAY_CLAIM = {
    "replay": {
        **REPLAY,
        "status": "claimed",
        "replay_execution_id": None,
        "completed_at": None,
        "comparison": None,
    },
    "bundle": {
        "original_execution": DETAIL,
        "recorded_calls": [
            {
                "step_name": "web_search",
                "step_type": "tool_call",
                "tool_name": "web_search",
                "occurrence": 1,
                "input": {"query": "q"},
                "output": {"data": []},
                "error": None,
            }
        ],
    },
}


def page(item: dict[str, Any]) -> dict[str, Any]:
    return {"items": [item], "total": 1, "limit": 50, "offset": 0}


STATS_OVERVIEW = {
    "window": "7d",
    "total_agents": 3,
    "total_executions": 80,
    "completed": 70,
    "failed": 8,
    "timed_out": 1,
    "running": 1,
    "success_rate": 0.886,
    "avg_duration_ms": 9800,
    "open_anomalies": 2,
}
STATS_TIMESERIES = {
    "window": "7d",
    "bucket": "day",
    "points": [
        {
            "bucket_start": "2026-11-14T00:00:00.000Z",
            "completed": 5,
            "failed": 1,
            "timed_out": 0,
            "avg_duration_ms": None,
        }
    ],
}
HEALTH = {
    "status": "ok",
    "version": "0.1.0",
    "database": "ok",
    "llm_provider": "rule_based",
    "llm_configured": True,
    "llm_model": None,
}
ERROR_ENVELOPE = {"error": {"code": "not_found", "message": "Execution does not exist.", "details": None}}

# (name, schema, valid example)
EXAMPLES: list[tuple[str, Any, dict[str, Any]]] = [
    ("Agent", Agent, AGENT),
    ("Page[Agent]", Page[Agent], page(AGENT)),
    ("ExecutionSummary", ExecutionSummary, SUMMARY),
    ("ExecutionDetail", ExecutionDetail, DETAIL),
    ("Page[ExecutionSummary]", Page[ExecutionSummary], page(SUMMARY)),
    ("IngestResponse", IngestResponse, {"accepted": 3, "duplicates": 0, "execution_status": "running"}),
    ("Trace", Trace, TRACE),
    ("Page[StoredEvent]", Page[StoredEvent], page(STORED_EVENT)),
    ("StatsOverview", StatsOverview, STATS_OVERVIEW),
    ("StatsTimeseries", StatsTimeseries, STATS_TIMESERIES),
    ("Anomaly", Anomaly, ANOMALY),
    ("Page[Anomaly]", Page[Anomaly], page(ANOMALY)),
    ("Investigation", Investigation, INVESTIGATION),
    ("Page[Investigation]", Page[Investigation], page(INVESTIGATION)),
    ("Replay", Replay, REPLAY),
    ("ReplayClaim", ReplayClaim, REPLAY_CLAIM),
    ("Health", Health, HEALTH),
    ("ErrorEnvelope", ErrorEnvelope, ERROR_ENVELOPE),
]
