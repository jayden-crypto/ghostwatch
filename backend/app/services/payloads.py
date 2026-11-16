"""Contract §0: any single payload field larger than 64 KB is stored as a truncation marker."""

import json
from typing import Any

MAX_FIELD_BYTES = 64 * 1024
PREVIEW_CHARS = 2000


def truncate_json(value: Any) -> Any:
    """The value itself, or the contract's marker when its JSON form is larger than 64 KB."""
    if value is None or isinstance(value, bool | int | float):
        return value
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    size = len(encoded.encode("utf-8"))
    if size <= MAX_FIELD_BYTES:
        return value
    preview = value if isinstance(value, str) else encoded
    return {"_truncated": True, "original_bytes": size, "preview": preview[:PREVIEW_CHARS]}


def cap_text(text: str | None, *, keep: str) -> str | None:
    """Bound a text field that must stay a string (error message, stack trace, log message).

    These fields cannot carry the object marker without breaking their type, so the text is cut to
    64 KB and says so. A stack trace keeps its tail, where the raising frame and the error are.
    """
    if text is None:
        return None
    size = len(text.encode("utf-8"))
    if size <= MAX_FIELD_BYTES:
        return text
    note = f"[truncated: {size} bytes in total]"
    if keep == "tail":
        return f"{note}\n{text[-MAX_FIELD_BYTES:]}"
    return f"{text[:MAX_FIELD_BYTES]}\n{note}"


def cap_error(error: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": error["type"],
        "message": cap_text(error["message"], keep="head"),
        "stacktrace": cap_text(error.get("stacktrace"), keep="tail"),
    }
