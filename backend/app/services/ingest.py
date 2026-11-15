"""Event ingestion: the only way execution state changes (contract §5).

`events` is the append-only evidentiary record. Steps, status and totals are derived from the new
events of a batch inside the same transaction that stores them, so they can never disagree.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import ids
from app.errors import ApiError, not_found
from app.models import Event, Execution, Step
from app.schemas import events as schemas
from app.services import replay as replay_service
from app.services.anomaly import engine as anomaly_engine
from app.services.anomaly.rules import StaleInfo
from app.services.anomaly.thresholds import DEFAULT_TIMEOUT_MS, SEVERITY_RANK
from app.services.investigation import engine as investigation_engine
from app.services.payloads import cap_error, cap_text, truncate_json
from app.timeutil import milliseconds_between, utcnow

TERMINAL_EVENT_STATUS = {
    "execution.completed": "completed",
    "execution.failed": "failed",
    "execution.timed_out": "timed_out",
}
_STEP_PAYLOADS = (schemas.StepStartedPayload, schemas.StepCompletedPayload, schemas.StepFailedPayload)


@dataclass(frozen=True)
class IngestResult:
    response: schemas.IngestResponse
    investigation_id: str | None  # queued by this batch; the caller runs it after the response


def ingest_events(session: Session, execution_id: str, events: list[schemas.IngestEvent]) -> IngestResult:
    # The savepoint makes the batch all-or-nothing: a rejected event leaves nothing behind.
    with session.begin_nested():
        # Locking the execution row serialises concurrent batches for the same execution, which
        # makes the duplicate check below safe and keeps step ordinals gapless.
        execution = session.scalars(
            select(Execution)
            .where(Execution.id == execution_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
        if execution is None:
            raise not_found("Execution", execution_id)

        new_events = _new_events_in_seq_order(session, execution_id, events)
        investigation_id = _apply(session, execution, new_events) if new_events else None
        response = schemas.IngestResponse(
            accepted=len(new_events),
            duplicates=len(events) - len(new_events),
            execution_status=execution.status,
        )
    session.commit()
    return IngestResult(response, investigation_id)


def _new_events_in_seq_order(
    session: Session, execution_id: str, events: list[schemas.IngestEvent]
) -> list[tuple[int, schemas.IngestEvent]]:
    """(index in the request, event) for events whose seq is not stored yet, sorted by seq.

    A seq repeated inside the batch keeps its first occurrence. Duplicates are dropped before any
    other rule runs, so a retried batch is always safe to resend, even after the execution ended.
    """
    stored = set(
        session.scalars(
            select(Event.seq).where(
                Event.execution_id == execution_id, Event.seq.in_({event.seq for event in events})
            )
        )
    )
    first_by_seq: dict[int, tuple[int, schemas.IngestEvent]] = {}
    for index, event in enumerate(events):
        if event.seq not in stored:
            first_by_seq.setdefault(event.seq, (index, event))
    return [first_by_seq[seq] for seq in sorted(first_by_seq)]


def stale_timeout_ms(config: dict[str, Any]) -> int:
    """How long an execution may go without an event before it counts as stale."""
    return config.get("timeout_ms") or DEFAULT_TIMEOUT_MS


def time_out_if_stale(session: Session, execution_id: str, now: datetime) -> bool:
    """Time out a running execution that has sent no event for its timeout. Used by the sweeper.

    State only ever changes through events, so this appends an `execution.timed_out` event and lets
    the normal terminal path run. The staleness check is repeated under the row lock, because an
    event may have arrived since the sweeper looked.
    """
    with session.begin_nested():
        execution = session.scalars(
            select(Execution)
            .where(Execution.id == execution_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
        if execution is None or execution.status != "running":
            return False
        timeout_ms = stale_timeout_ms(execution.config)
        idle_ms = milliseconds_between(execution.last_event_at, now)
        if idle_ms < timeout_ms:
            return False
        last_seq = session.scalar(select(func.max(Event.seq)).where(Event.execution_id == execution_id))
        event = schemas.ExecutionTimedOut(
            seq=(last_seq or 0) + 1, type="execution.timed_out", timestamp=now, payload={}
        )
        stale = StaleInfo(last_event_at=execution.last_event_at, timeout_ms=timeout_ms, idle_ms=idle_ms)
        _apply(session, execution, [(0, event)], stale=stale)
    session.commit()
    return True


def _apply(
    session: Session,
    execution: Execution,
    new_events: list[tuple[int, schemas.IngestEvent]],
    *,
    stale: StaleInfo | None = None,
) -> str | None:
    """Store and apply the events. Returns the id of the investigation a terminal event queued, if any."""
    received_at = utcnow()
    investigation_id = None
    referenced = {
        event.payload.step_id for _, event in new_events if isinstance(event.payload, _STEP_PAYLOADS)
    }
    known_steps = {step.id: step for step in session.scalars(select(Step).where(Step.id.in_(referenced)))}

    for index, event in new_events:
        if execution.status != "running" and event.type != "log":
            raise ApiError(
                409,
                "execution_already_terminal",
                f"Execution {execution.id} is already {execution.status}; only log events are accepted.",
                {"execution_status": execution.status, "rejected_seq": event.seq},
            )
        payload = _stored_payload(event)
        session.add(
            Event(
                id=ids.new_id(ids.EVENT),
                execution_id=execution.id,
                seq=event.seq,
                type=event.type,
                timestamp=event.timestamp,
                received_at=received_at,
                payload=payload,
            )
        )
        if isinstance(event, schemas.StepStarted):
            _start_step(session, execution, known_steps, index, event, payload)
        elif isinstance(event, schemas.StepCompleted | schemas.StepFailed):
            _end_step(execution, known_steps, index, event, payload)
        elif event.type in TERMINAL_EVENT_STATUS:
            investigation_id = _finalize(session, execution, event, payload, stale)

    execution.last_event_at = received_at
    return investigation_id


def _stored_payload(event: schemas.IngestEvent) -> dict[str, Any]:
    """The payload as stored in the event log: defaults filled in, oversized fields truncated."""
    payload = event.payload.model_dump(mode="json")
    for field in ("input", "output", "metadata"):
        if field in payload:
            payload[field] = truncate_json(payload[field])
    if "error" in payload:
        payload["error"] = cap_error(payload["error"])
    if isinstance(event, schemas.Log):
        payload["message"] = cap_text(payload["message"], keep="head")
    return payload


def _invalid_step(index: int, message: str) -> ApiError:
    return ApiError(
        422,
        "validation_error",
        "Request validation failed.",
        [{"loc": ["body", "events", index, "payload", "step_id"], "msg": message}],
    )


def _start_step(
    session: Session,
    execution: Execution,
    known_steps: dict[str, Step],
    index: int,
    event: schemas.StepStarted,
    payload: dict[str, Any],
) -> None:
    if event.payload.step_id in known_steps:
        raise _invalid_step(index, f"step {event.payload.step_id} has already been started")
    execution.step_count += 1
    step = Step(
        id=event.payload.step_id,
        execution_id=execution.id,
        parent_step_id=event.payload.parent_step_id,
        ordinal=execution.step_count,
        name=event.payload.name,
        type=event.payload.step_type,
        status="running",
        started_at=event.timestamp,
        input=payload["input"],
        tool_name=event.payload.tool_name,
        model=event.payload.model,
        attempt=event.payload.attempt,
        metadata_=payload["metadata"],
    )
    session.add(step)
    known_steps[step.id] = step


def _end_step(
    execution: Execution,
    known_steps: dict[str, Step],
    index: int,
    event: schemas.StepCompleted | schemas.StepFailed,
    payload: dict[str, Any],
) -> None:
    step = known_steps.get(event.payload.step_id)
    if step is None or step.execution_id != execution.id:
        raise _invalid_step(index, f"step {event.payload.step_id} was never started in this execution")
    if step.status != "running":
        raise _invalid_step(index, f"step {event.payload.step_id} is already {step.status}")
    step.ended_at = event.timestamp
    step.duration_ms = milliseconds_between(step.started_at, event.timestamp)
    step.output = payload["output"]
    if isinstance(event, schemas.StepCompleted):
        step.status = "completed"
        step.tokens_input = event.payload.tokens_input
        step.tokens_output = event.payload.tokens_output
        step.metadata_ = _merged_metadata(step.metadata_, payload["metadata"])
    else:
        step.status = "failed"
        step.error = payload["error"]


def _merged_metadata(started: dict[str, Any], completed: dict[str, Any]) -> dict[str, Any]:
    """Metadata from step.completed is laid over the metadata from step.started."""
    if not completed:
        return started
    if started.get("_truncated") is True or completed.get("_truncated") is True:
        return completed  # a truncation marker cannot be merged key by key; the later value wins
    return truncate_json({**started, **completed})


def _finalize(
    session: Session,
    execution: Execution,
    event: schemas.IngestEvent,
    payload: dict[str, Any],
    stale: StaleInfo | None,
) -> str | None:
    """Apply a terminal event: status, end time, duration and token totals, then run the anomaly rules."""
    execution.status = TERMINAL_EVENT_STATUS[event.type]
    execution.ended_at = event.timestamp
    execution.duration_ms = milliseconds_between(execution.started_at, event.timestamp)
    if isinstance(event, schemas.ExecutionCompleted):
        execution.output = payload["output"]
    elif isinstance(event, schemas.ExecutionFailed):
        execution.error = payload["error"]
    else:
        execution.error = _timeout_error(execution.duration_ms)

    # SUM ignores NULLs and is NULL when no step reported tokens: unknown stays unknown.
    execution.tokens_input, execution.tokens_output = session.execute(
        select(func.sum(Step.tokens_input), func.sum(Step.tokens_output)).where(
            Step.execution_id == execution.id
        )
    ).one()

    raised = anomaly_engine.evaluate(session, execution, stale=stale)

    # Contract §5 rule 5: investigate every failure, and every run with an anomaly of high severity or above.
    trigger = None
    if execution.status in ("failed", "timed_out"):
        trigger = "auto_failure"
    elif any(SEVERITY_RANK[anomaly.severity] >= SEVERITY_RANK["high"] for anomaly in raised):
        trigger = "auto_anomaly"
    investigation_id = investigation_engine.queue(session, execution, trigger).id if trigger else None

    # If this execution is the run of a replay, the replay is now complete and can be compared.
    replay_service.complete_for_execution(session, execution)
    return investigation_id


def _timeout_error(duration_ms: int) -> dict[str, Any]:
    return {
        "type": "TimeoutError",
        "message": f"Execution timed out after {duration_ms} ms.",
        "stacktrace": None,
    }
