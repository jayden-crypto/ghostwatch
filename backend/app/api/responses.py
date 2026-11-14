"""Error responses for the OpenAPI document: every non-2xx body is the contract's error envelope."""

from typing import Any

from app.schemas.common import ErrorEnvelope

_DESCRIPTIONS = {
    400: "`bad_request`: the `sort` value names a field this endpoint cannot sort by.",
    401: "`unauthorized`: the `Authorization: Bearer <key>` header is missing or wrong.",
    404: "`not_found`: no resource has this id.",
    422: "`validation_error`: `details` lists each problem as `{loc, msg}`.",
    500: "`internal_error`: an unexpected failure. The body never contains a stack trace.",
}


def errors(*statuses: int | tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    """`responses=errors(404, (409, "why this endpoint conflicts"))` for a route decorator."""
    documented: dict[int | str, dict[str, Any]] = {}
    for status in statuses:
        code, description = status if isinstance(status, tuple) else (status, _DESCRIPTIONS[status])
        documented[code] = {"model": ErrorEnvelope, "description": description}
    return documented
