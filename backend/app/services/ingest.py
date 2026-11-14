"""Event ingestion: the only way execution state changes (contract §5).

`events` is the append-only evidentiary record. Steps, status and totals are derived from the new
events of a batch inside the same transaction that stores them, so they can never disagree.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import ids
from app.errors import ApiError, not_found
from app.models import Event, Execution, Step
from app.schemas import events as schemas
from app.services.payloads import cap_error, cap_text, truncate_json
from app.timeutil import milliseconds_between, utcnow

TERMINAL_EVENT_STATUS = {
    "execution.completed": "completed",
    "execution.failed": "failed",
    "execution.timed_out": "timed_out",
}
_STEP_PAYLOADS = (schemas.StepStartedPayload, schemas.StepCompletedPayload, schemas.StepFailedPayload)


def ingest_events(
    session: Session, execution_id: str, events: list[schemas.IngestEvent]
) -> schemas.IngestResponse:
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
        if new_events:
            _apply(session, execution, new_events)
        response = schemas.IngestResponse(
            accepted=len(new_events),
            duplicates=len(events) - len(new_events),
            execution_status=execution.status,
        )
    session.commit()
    return response


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


def _apply(session: Session, execution: Execution, new_events: list[tuple[int, schemas.IngestEvent]]) -> None:
    received_at = utcnow()
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
            _finalize(session, execution, event, payload)

    execution.last_event_at = received_at


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
    session: Session, execution: Execution, event: schemas.IngestEvent, payload: dict[str, Any]
) -> None:
    """Apply a terminal event: status, end time, duration and token totals."""
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


def _timeout_error(duration_ms: int) -> dict[str, Any]:
    return {
        "type": "TimeoutError",
        "message": f"Execution timed out after {duration_ms} ms.",
        "stacktrace": None,
    }
