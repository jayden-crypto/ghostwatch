"""Replay coordination (contract §10): record the request, hand a worker the bundle, compare the result.

The backend never runs agent code. A worker claims a replay, re-runs the agent in its own process
and streams the run as an ordinary execution linked through `replay_of` and `replay_id`. When that
execution ends, the comparison with the original is computed here from stored rows.
"""

from collections import Counter
from collections.abc import Sequence
from typing import Any, get_args

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import ids, models
from app.errors import ApiError, not_found
from app.schemas.common import Page
from app.schemas.enums import ReplaySource, ReplayStatus
from app.schemas.replays import Replay, ReplayBundle, ReplayClaim, ReplayCreate
from app.services.executions import build_detail, build_summaries, get_execution, tokens_total
from app.services.investigation.facts import find_failing_step
from app.services.query import parse_csv, parse_sort
from app.timeutil import utcnow

SORTABLE = {"requested_at": models.Replay.requested_at}
RECORDED_STEP_TYPES = ("tool_call", "llm_call")  # the calls a sandbox replay serves from the recording


def to_schema(replay: models.Replay) -> Replay:
    return Replay(
        id=replay.id,
        original_execution_id=replay.original_execution_id,
        replay_execution_id=replay.replay_execution_id,
        mode=replay.mode,
        status=replay.status,
        side_effects_authorized=replay.side_effects_authorized,
        note=replay.note,
        requested_at=replay.requested_at,
        claimed_at=replay.claimed_at,
        completed_at=replay.completed_at,
        error=replay.error,
        comparison=replay.comparison,
    )


def get_replay(session: Session, replay_id: str) -> models.Replay:
    replay = session.get(models.Replay, replay_id)
    if replay is None:
        raise not_found("Replay", replay_id)
    return replay


def create_replay(session: Session, execution_id: str, body: ReplayCreate) -> models.Replay:
    execution = get_execution(session, execution_id)
    if body.mode == "live" and not body.authorize_side_effects:
        raise ApiError(
            422,
            "side_effect_authorization_required",
            "A live replay runs the agent's tools for real. Set authorize_side_effects to true to confirm, "
            "or use mode sandbox.",
        )
    if execution.status == "running":
        raise ApiError(
            409, "conflict", f"Execution {execution_id} is still running; it can be replayed once it ends."
        )
    replay = models.Replay(
        id=ids.new_id(ids.REPLAY),
        original_execution_id=execution.id,
        mode=body.mode,
        status="pending",
        # Authorization only means something for a live replay; a sandbox replay never has it.
        side_effects_authorized=body.mode == "live",
        note=body.note,
        requested_at=utcnow(),
    )
    session.add(replay)
    session.commit()
    return replay


def list_replays(
    session: Session,
    *,
    original_execution_id: str | None,
    status: str | None,
    sort: str,
    limit: int,
    offset: int,
) -> Page[Replay]:
    statuses = parse_csv(status, get_args(ReplayStatus), "status")
    order = parse_sort(sort, SORTABLE)
    conditions = []
    if original_execution_id is not None:
        conditions.append(models.Replay.original_execution_id == original_execution_id)
    if statuses is not None:
        conditions.append(models.Replay.status.in_(statuses))
    total = session.scalar(select(func.count()).select_from(models.Replay).where(*conditions))
    replays = session.scalars(
        select(models.Replay).where(*conditions).order_by(order, models.Replay.id).limit(limit).offset(offset)
    ).all()
    return Page(items=[to_schema(replay) for replay in replays], total=total, limit=limit, offset=offset)


def claim_replay(session: Session, replay_id: str) -> ReplayClaim:
    """Hand the replay to one worker. The conditional UPDATE lets exactly one of two racing claims win."""
    claimed = session.scalar(
        update(models.Replay)
        .where(models.Replay.id == replay_id, models.Replay.status == "pending")
        .values(status="claimed", claimed_at=utcnow())
        .returning(models.Replay.id)
    )
    if claimed is None:
        replay = get_replay(session, replay_id)  # 404 if it does not exist at all
        raise ApiError(
            409, "conflict", f"Replay {replay_id} is already {replay.status}; it cannot be claimed."
        )
    session.commit()
    replay = session.get(models.Replay, replay_id, populate_existing=True)
    return ReplayClaim(replay=to_schema(replay), bundle=build_bundle(session, replay))


def build_bundle(session: Session, replay: models.Replay) -> ReplayBundle:
    """The original execution and its recorded tool and LLM calls, in the order they happened.

    `occurrence` numbers the calls that share a step type and a tool name (or step name, for LLM
    calls), so the worker can match the n-th call of a tool to the n-th recording.
    """
    original = session.get(models.Execution, replay.original_execution_id)
    steps = session.scalars(
        select(models.Step)
        .where(models.Step.execution_id == original.id, models.Step.type.in_(RECORDED_STEP_TYPES))
        .order_by(models.Step.ordinal)
    ).all()
    seen: Counter[tuple[str, str]] = Counter()
    recorded_calls = []
    for step in steps:
        key = (step.type, step.tool_name or step.name)
        seen[key] += 1
        recorded_calls.append(
            {
                "step_name": step.name,
                "step_type": step.type,
                "tool_name": step.tool_name,
                "occurrence": seen[key],
                "input": step.input,
                "output": step.output,
                "error": step.error,
            }
        )
    return ReplayBundle(original_execution=build_detail(session, original), recorded_calls=recorded_calls)


def _failure_key(execution: models.Execution, steps: Sequence[models.Step]) -> tuple[str | None, str | None]:
    """What a failure is identified by when two runs are compared: the failing step's name and the error type."""
    step = find_failing_step(execution, steps)
    error = (step.error if step is not None else None) or execution.error or {}
    return (step.name if step is not None else None, error.get("type"))


def determine_outcome(
    original: models.Execution,
    original_steps: Sequence[models.Step],
    replay: models.Execution,
    replay_steps: Sequence[models.Step],
) -> str:
    """Contract §10 outcome rule."""
    statuses = (original.status, replay.status)
    if "timed_out" in statuses or "running" in statuses:
        return "inconclusive"
    if statuses == ("failed", "completed"):
        return "fixed"
    if statuses == ("completed", "failed"):
        return "regressed"
    if statuses == ("completed", "completed"):
        return "both_succeeded"
    same = _failure_key(original, original_steps) == _failure_key(replay, replay_steps)
    return "same_failure" if same else "different_failure"


def _replay_source(step: models.Step) -> str | None:
    source = step.metadata_.get("replay_source")
    return source if source in get_args(ReplaySource) else None


def diff_steps(
    original_steps: Sequence[models.Step], replay_steps: Sequence[models.Step]
) -> list[dict[str, Any]]:
    """Steps aligned by (ordinal, name). A different name at the same ordinal is a removal plus an addition."""
    originals = {step.ordinal: step for step in original_steps}
    replays = {step.ordinal: step for step in replay_steps}
    diffs: list[dict[str, Any]] = []

    def diff(
        ordinal: int, name: str, change: str, original: models.Step | None, replay: models.Step | None
    ) -> None:
        diffs.append(
            {
                "ordinal": ordinal,
                "name": name,
                "original_step_id": original.id if original else None,
                "replay_step_id": replay.id if replay else None,
                "change": change,
                "original_status": original.status if original else None,
                "replay_status": replay.status if replay else None,
                "replay_source": _replay_source(replay) if replay else None,
            }
        )

    for ordinal in sorted(originals.keys() | replays.keys()):
        original, replay = originals.get(ordinal), replays.get(ordinal)
        if original is not None and replay is not None and original.name == replay.name:
            if original.status != replay.status:
                change = "status_changed"
            elif original.output != replay.output:
                change = "output_changed"
            else:
                change = "unchanged"
            diff(ordinal, original.name, change, original, replay)
            continue
        if original is not None:
            diff(ordinal, original.name, "removed", original, None)
        if replay is not None:
            diff(ordinal, replay.name, "added", None, replay)
    return diffs


def _steps(session: Session, execution_id: str) -> Sequence[models.Step]:
    return session.scalars(
        select(models.Step).where(models.Step.execution_id == execution_id).order_by(models.Step.ordinal)
    ).all()


def complete_for_execution(session: Session, execution: models.Execution) -> None:
    """Called when an execution ends: if it is the run of a replay, finish the replay and compare."""
    if execution.replay_id is None:
        return
    replay = session.get(models.Replay, execution.replay_id)
    if replay is None or replay.replay_execution_id != execution.id or replay.status != "claimed":
        return
    original = session.get(models.Execution, replay.original_execution_id)
    original_steps, replay_steps = _steps(session, original.id), _steps(session, execution.id)
    original_summary, replay_summary = build_summaries(session, [original, execution])
    original_tokens, replay_tokens = tokens_total(original), tokens_total(execution)
    measured = original.duration_ms is not None and execution.duration_ms is not None
    replay.comparison = {
        "original": original_summary.model_dump(mode="json"),
        "replay": replay_summary.model_dump(mode="json"),
        "outcome": determine_outcome(original, original_steps, execution, replay_steps),
        "duration_delta_ms": execution.duration_ms - original.duration_ms if measured else None,
        "tokens_delta": (
            replay_tokens - original_tokens
            if original_tokens is not None and replay_tokens is not None
            else None
        ),
        "step_count_delta": execution.step_count - original.step_count,
        "step_diffs": diff_steps(original_steps, replay_steps),
    }
    replay.status = "completed"
    replay.completed_at = utcnow()
