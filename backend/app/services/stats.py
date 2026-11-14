"""Stats: aggregates over stored executions and anomalies.

A window is a whole number of UTC-aligned buckets ending with the current, still-filling one:
24h = this hour and the 23 before it; 7d = today and the 6 days before it. The overview uses the
window's default bucket, so its totals always equal the sum of the default timeseries.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.models import Agent, Anomaly, Execution
from app.schemas.enums import TERMINAL_STATUSES
from app.schemas.stats import Bucket, StatsOverview, StatsTimeseries, TimeseriesPoint, Window
from app.services.agents import get_agent
from app.timeutil import utcnow

WINDOW_LENGTH = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
BUCKET_LENGTH = {"hour": timedelta(hours=1), "day": timedelta(days=1)}
DEFAULT_BUCKET: dict[str, Bucket] = {"24h": "hour", "7d": "day", "30d": "day"}


def bucket_starts(window: Window, bucket: Bucket, now: datetime) -> list[datetime]:
    """Start of every bucket in the window, oldest first; the last one contains `now`."""
    now = now.astimezone(UTC)
    current = now.replace(minute=0, second=0, microsecond=0)
    if bucket == "day":
        current = current.replace(hour=0)
    length = BUCKET_LENGTH[bucket]
    count = max(WINDOW_LENGTH[window] // length, 1)
    return [current - (count - 1 - index) * length for index in range(count)]


def get_overview(session: Session, window: Window, now: datetime | None = None) -> StatsOverview:
    now = now or utcnow()
    since = bucket_starts(window, DEFAULT_BUCKET[window], now)[0]
    counts = dict(
        session.execute(
            select(Execution.status, func.count())
            .where(Execution.started_at >= since, Execution.started_at <= now)
            .group_by(Execution.status)
        ).all()
    )
    completed, failed, timed_out = (counts.get(status, 0) for status in TERMINAL_STATUSES)
    terminal = completed + failed + timed_out
    average = session.scalar(
        select(func.avg(Execution.duration_ms)).where(
            Execution.started_at >= since,
            Execution.started_at <= now,
            Execution.status.in_(TERMINAL_STATUSES),
        )
    )
    return StatsOverview(
        window=window,
        total_agents=session.scalar(select(func.count()).select_from(Agent)),
        total_executions=terminal + counts.get("running", 0),
        completed=completed,
        failed=failed,
        timed_out=timed_out,
        running=counts.get("running", 0),
        success_rate=completed / terminal if terminal else None,
        avg_duration_ms=None if average is None else round(average),
        # Open anomalies are current state, not history, so they are not limited to the window.
        open_anomalies=session.scalar(
            select(func.count()).select_from(Anomaly).where(Anomaly.status == "open")
        ),
    )


def get_timeseries(
    session: Session, window: Window, bucket: Bucket | None, agent_id: str | None, now: datetime | None = None
) -> StatsTimeseries:
    now = now or utcnow()
    bucket = bucket or DEFAULT_BUCKET[window]
    starts = bucket_starts(window, bucket, now)
    if agent_id is not None:
        get_agent(session, agent_id)

    # Literal SQL (not bind parameters) so the SELECT and GROUP BY expressions are textually identical.
    # `bucket` is safe to inline: bucket_starts() above has already looked it up in BUCKET_LENGTH.
    bucket_start = func.date_trunc(
        literal_column(f"'{bucket}'"), Execution.started_at, literal_column("'UTC'")
    )
    query = (
        select(
            bucket_start,
            func.count().filter(Execution.status == "completed"),
            func.count().filter(Execution.status == "failed"),
            func.count().filter(Execution.status == "timed_out"),
            func.avg(Execution.duration_ms).filter(Execution.status.in_(TERMINAL_STATUSES)),
        )
        .where(Execution.started_at >= starts[0], Execution.started_at <= now)
        .group_by(bucket_start)
    )
    if agent_id is not None:
        query = query.where(Execution.agent_id == agent_id)
    rows = {row[0].astimezone(UTC): row for row in session.execute(query)}

    # Every bucket is returned, with zeros where nothing ran, so charts never have gaps.
    points = []
    for start in starts:
        _, completed, failed, timed_out, average = rows.get(start, (start, 0, 0, 0, None))
        points.append(
            TimeseriesPoint(
                bucket_start=start,
                completed=completed,
                failed=failed,
                timed_out=timed_out,
                avg_duration_ms=None if average is None else round(average),
            )
        )
    return StatsTimeseries(window=window, bucket=bucket, points=points)
