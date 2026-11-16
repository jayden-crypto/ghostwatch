"""Building contract Evidence items (contract §2). Values are copied from stored data, never generated."""

import json
from typing import Any

EXCERPT_LIMIT = 500


def evidence_item(
    kind: str,
    label: str,
    *,
    ref_id: str | None = None,
    field: str | None = None,
    observed: Any = None,
    expected: Any = None,
    excerpt: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "ref_id": ref_id,
        "field": field,
        "observed": observed,
        "expected": expected,
        "excerpt": None if excerpt is None else excerpt[:EXCERPT_LIMIT],
    }


def json_excerpt(value: Any) -> str:
    """The start of a stored JSON value, serialised compactly, for use as a verbatim excerpt."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text[:EXCERPT_LIMIT]
