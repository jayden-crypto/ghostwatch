"""Helpers for the query parameters the contract uses on list endpoints."""

from collections.abc import Collection, Mapping
from typing import Any

from sqlalchemy import ColumnElement

from app.errors import ApiError, invalid_query


def parse_csv(value: str | None, allowed: Collection[str], param: str) -> list[str] | None:
    """A comma-separated list of enum values, or None when the parameter is absent."""
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [item for item in items if item not in allowed]
    if not items or unknown:
        choices = ", ".join(sorted(allowed))
        raise invalid_query(param, f"must be a comma-separated list of: {choices}")
    return items


def parse_sort(sort: str, allowed: Mapping[str, ColumnElement[Any]]) -> ColumnElement[Any]:
    """`field` or `-field` (descending). Nulls sort last in both directions."""
    descending = sort.startswith("-")
    field = sort[1:] if descending else sort
    if field not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ApiError(
            400,
            "bad_request",
            f"Cannot sort by {field!r}. Allowed: {choices} (prefix with - for descending).",
        )
    column = allowed[field]
    return (column.desc() if descending else column.asc()).nulls_last()


def contains(column: ColumnElement[Any], text: str) -> ColumnElement[bool]:
    """Case-insensitive substring match with LIKE wildcards in the search text escaped."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")
