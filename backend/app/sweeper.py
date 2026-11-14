"""Stale-execution sweeper: an execution that stops sending events is timed out, not left running forever.

Contract §8 `stale_execution`: status `running` with no event received for `config.timeout_ms`
(default 300000). The sweeper marks it `timed_out` and the anomaly is recorded.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import new_session, session_scope
from app.models import Execution
from app.services import ingest
from app.services.investigation import engine as investigation_engine
from app.timeutil import milliseconds_between, utcnow

logger = logging.getLogger("ghostwatch")


def sweep_stale_executions(session: Session, now: datetime | None = None) -> int:
    """One pass over the running executions. Returns how many were timed out."""
    now = now or utcnow()
    running = session.execute(
        select(Execution.id, Execution.last_event_at, Execution.config).where(Execution.status == "running")
    ).all()
    timed_out = 0
    for execution_id, last_event_at, config in running:
        if milliseconds_between(last_event_at, now) < ingest.stale_timeout_ms(config):
            continue
        try:
            if ingest.time_out_if_stale(session, execution_id, now):
                timed_out += 1
                logger.info("Sweeper timed out stale execution %s", execution_id)
        except Exception:
            # One bad execution must not stop the others from being swept. Its own savepoint has
            # already been rolled back by time_out_if_stale.
            logger.exception("Sweeper could not time out execution %s", execution_id)
    return timed_out


def _sweep_once() -> None:
    with new_session() as session:
        sweep_stale_executions(session)
    # Timing an execution out queues its investigation. Running queued ones here also picks up any
    # that were queued just before a restart.
    investigation_engine.run_queued(session_scope)


async def run_sweeper(
    interval_seconds: float, stop: asyncio.Event, sweep: Callable[[], None] = _sweep_once
) -> None:
    """Sweep, wait `interval_seconds`, repeat, until `stop` is set. A failed pass is logged, not fatal."""
    while not stop.is_set():
        try:
            await asyncio.to_thread(sweep)
        except Exception:
            logger.exception("Stale-execution sweep failed; retrying in %s s", interval_seconds)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
