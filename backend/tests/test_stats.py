"""Contract §7: stats overview and timeseries."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.stats import bucket_starts, get_overview, get_timeseries
from app.timeutil import format_timestamp
from tests.factories import make_agent, make_anomaly, make_execution

NOW = datetime(2026, 11, 14, 13, 5, 30, tzinfo=UTC)
OVERVIEW_KEYS = {
    "window", "total_agents", "total_executions", "completed", "failed", "timed_out", "running",
    "success_rate", "avg_duration_ms", "open_anomalies",
}  # fmt: skip
POINT_KEYS = {"bucket_start", "completed", "failed", "timed_out", "avg_duration_ms"}


def utc(day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, second, tzinfo=UTC)


@pytest.mark.parametrize(
    ("window", "bucket", "count", "first", "last"),
    [
        ("24h", "hour", 24, utc(13, 14), utc(14, 13)),
        ("7d", "day", 7, utc(8), utc(14)),
        ("30d", "day", 30, datetime(2026, 10, 16, tzinfo=UTC), utc(14)),
        ("7d", "hour", 168, utc(7, 14), utc(14, 13)),
        ("30d", "hour", 720, datetime(2026, 10, 15, 14, tzinfo=UTC), utc(14, 13)),
        ("24h", "day", 1, utc(14), utc(14)),
    ],
)
def test_bucket_starts(window: str, bucket: str, count: int, first: datetime, last: datetime) -> None:
    starts = bucket_starts(window, bucket, NOW)
    assert (len(starts), starts[0], starts[-1]) == (count, first, last)
    step = timedelta(hours=1) if bucket == "hour" else timedelta(days=1)
    assert all(later - earlier == step for earlier, later in zip(starts, starts[1:], strict=False))


def test_bucket_starts_are_utc_whatever_the_callers_offset() -> None:
    kolkata = NOW.astimezone(datetime.strptime("+0530", "%z").tzinfo)
    assert bucket_starts("7d", "day", kolkata) == bucket_starts("7d", "day", NOW)


def test_empty_database(db_session: Session) -> None:
    overview = get_overview(db_session, "7d", NOW)
    assert overview.model_dump() == {
        "window": "7d",
        "total_agents": 0,
        "total_executions": 0,
        "completed": 0,
        "failed": 0,
        "timed_out": 0,
        "running": 0,
        "success_rate": None,
        "avg_duration_ms": None,
        "open_anomalies": 0,
    }
    series = get_timeseries(db_session, "7d", None, None, NOW)
    assert (series.window, series.bucket, len(series.points)) == ("7d", "day", 7)
    assert all(
        (point.completed, point.failed, point.timed_out, point.avg_duration_ms) == (0, 0, 0, None)
        for point in series.points
    )


@pytest.fixture
def history(db_session: Session) -> dict:
    """Executions placed on and around bucket and window edges, relative to NOW (14 Nov 13:05:30 UTC)."""
    research = make_agent(db_session, slug="research-assistant")
    invoice = make_agent(db_session, slug="invoice-processor")
    make_agent(db_session, slug="idle-agent")
    rows = [
        (research, "completed", utc(14, 13, 0, 0), 1000),  # first instant of the current hour
        (research, "failed", utc(14, 12, 59, 59), 3000),  # last second of the previous hour
        (research, "completed", utc(14, 0, 0, 0), 2000),  # first instant of today
        (invoice, "timed_out", utc(13, 23, 59, 59), 300000),  # last second of yesterday
        (invoice, "completed", utc(13, 14, 0, 0), 500),  # first instant of the 24h window
        (invoice, "completed", utc(13, 13, 59, 59), 700),  # one second before the 24h window
        (research, "running", utc(14, 13, 5, 0), None),  # running: counted in overview, not in points
        (research, "completed", utc(8, 0, 0, 0), 4000),  # first instant of the 7d window
        (research, "failed", utc(7, 23, 59, 59), 9000),  # one second before the 7d window
        (invoice, "completed", utc(14, 13, 6, 0), 100),  # after NOW: not counted
    ]
    for agent, status, started_at, duration in rows:
        make_execution(db_session, agent, status=status, started_at=started_at, duration_ms=duration)
    latest = make_execution(db_session, invoice, status="completed", started_at=utc(1), duration_ms=1)
    make_anomaly(db_session, latest)  # old but still open
    make_anomaly(db_session, latest, type="duration_spike", status="resolved")
    return {"research": research, "invoice": invoice}


def test_overview_windows(db_session: Session, history: dict) -> None:
    day = get_overview(db_session, "24h", NOW)
    assert (day.total_agents, day.open_anomalies) == (3, 1)
    assert (day.completed, day.failed, day.timed_out, day.running, day.total_executions) == (3, 1, 1, 1, 6)
    assert day.success_rate == pytest.approx(3 / 5)
    assert day.avg_duration_ms == round((1000 + 3000 + 2000 + 300000 + 500) / 5)

    week = get_overview(db_session, "7d", NOW)
    assert (week.completed, week.failed, week.timed_out, week.running, week.total_executions) == (
        5,
        1,
        1,
        1,
        8,
    )

    month = get_overview(db_session, "30d", NOW)
    assert (month.completed, month.failed, month.timed_out, month.running, month.total_executions) == (
        6,
        2,
        1,
        1,
        10,
    )


def test_timeseries_hourly_bucket_edges(db_session: Session, history: dict) -> None:
    series = get_timeseries(db_session, "24h", None, None, NOW)
    assert (series.bucket, len(series.points)) == ("hour", 24)
    points = {point.bucket_start: point for point in series.points}
    assert [point.bucket_start for point in series.points] == sorted(points)

    def values(start: datetime) -> tuple:
        point = points[start]
        return (point.completed, point.failed, point.timed_out, point.avg_duration_ms)

    assert values(utc(14, 13)) == (1, 0, 0, 1000)  # the running execution is not a point
    assert values(utc(14, 12)) == (0, 1, 0, 3000)
    assert values(utc(14, 0)) == (1, 0, 0, 2000)
    assert values(utc(13, 23)) == (0, 0, 1, 300000)
    assert values(utc(13, 14)) == (1, 0, 0, 500)
    assert values(utc(14, 5)) == (0, 0, 0, None)
    assert utc(13, 13) not in points

    overview = get_overview(db_session, "24h", NOW)
    assert sum(point.completed for point in series.points) == overview.completed
    assert sum(point.failed for point in series.points) == overview.failed
    assert sum(point.timed_out for point in series.points) == overview.timed_out


def test_timeseries_daily_and_agent_filter(db_session: Session, history: dict) -> None:
    series = get_timeseries(db_session, "7d", None, None, NOW)
    by_day = {
        point.bucket_start.day: (point.completed, point.failed, point.timed_out) for point in series.points
    }
    assert by_day == {
        8: (1, 0, 0),
        9: (0, 0, 0),
        10: (0, 0, 0),
        11: (0, 0, 0),
        12: (0, 0, 0),
        13: (2, 0, 1),
        14: (2, 1, 0),
    }
    today = series.points[-1]
    assert today.avg_duration_ms == round((1000 + 3000 + 2000) / 3)

    research_only = get_timeseries(db_session, "7d", "day", history["research"].id, NOW)
    by_day = {
        point.bucket_start.day: (point.completed, point.failed, point.timed_out)
        for point in research_only.points
    }
    assert (by_day[13], by_day[14], by_day[8]) == ((0, 0, 0), (2, 1, 0), (1, 0, 0))
    assert len(research_only.points) == 7


def test_stats_endpoints(db_client: TestClient, db_session: Session) -> None:
    agent = make_agent(db_session)
    now = datetime.now(UTC)
    make_execution(
        db_session, agent, status="completed", started_at=now - timedelta(minutes=1), duration_ms=250
    )
    make_execution(db_session, agent, status="failed", started_at=now - timedelta(days=20), duration_ms=750)

    overview = db_client.get("/api/v1/stats/overview")
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert set(body) == OVERVIEW_KEYS
    assert (body["window"], body["total_agents"], body["total_executions"], body["completed"]) == (
        "7d",
        1,
        1,
        1,
    )
    assert (body["success_rate"], body["avg_duration_ms"]) == (1.0, 250)
    assert db_client.get("/api/v1/stats/overview?window=30d").json()["total_executions"] == 2

    series = db_client.get("/api/v1/stats/timeseries?window=24h").json()
    assert set(series) == {"window", "bucket", "points"}
    assert (series["window"], series["bucket"], len(series["points"])) == ("24h", "hour", 24)
    assert all(set(point) == POINT_KEYS for point in series["points"])
    current_hour = (now - timedelta(minutes=1)).replace(minute=0, second=0, microsecond=0)
    counted = [point for point in series["points"] if point["completed"]]
    assert [(point["bucket_start"], point["completed"], point["avg_duration_ms"]) for point in counted] == [
        (format_timestamp(current_hour), 1, 250)
    ]
    assert len(db_client.get("/api/v1/stats/timeseries?window=30d&bucket=hour").json()["points"]) == 720
    filtered = db_client.get(f"/api/v1/stats/timeseries?agent_id={agent.id}").json()
    assert (filtered["bucket"], len(filtered["points"])) == ("day", 7)


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/stats/overview?window=1y", 422, "validation_error"),
        ("/stats/timeseries?window=7d&bucket=minute", 422, "validation_error"),
        ("/stats/timeseries?agent_id=agt_" + "0" * 32, 404, "not_found"),
    ],
)
def test_stats_reject_bad_parameters(
    db_client: TestClient, db_session: Session, path: str, status: int, code: str
) -> None:
    response = db_client.get(f"/api/v1{path}")
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
