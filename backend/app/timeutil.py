"""UTC time helpers. Every stored and returned timestamp is UTC (contract §0)."""

from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    return datetime.now(UTC)


def format_timestamp(value: datetime) -> str:
    """ISO 8601, UTC, millisecond precision, Z suffix: 2026-11-14T10:32:05.123Z."""
    value = value.astimezone(UTC)
    return f"{value:%Y-%m-%dT%H:%M:%S}.{value.microsecond // 1000:03d}Z"


def milliseconds_between(start: datetime, end: datetime) -> int:
    """Whole milliseconds from start to end, never negative (client clocks can run backwards)."""
    return max((end - start) // timedelta(milliseconds=1), 0)
