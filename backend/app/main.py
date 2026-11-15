"""Application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.responses import errors
from app.api.v1 import router as v1_router
from app.config import get_settings
from app.errors import UnhandledErrorMiddleware, register_error_handlers
from app.sweeper import run_sweeper


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run the stale-execution sweeper for as long as the app is up."""
    stop = asyncio.Event()
    sweeper = asyncio.create_task(run_sweeper(get_settings().sweeper_interval_seconds, stop))
    try:
        yield
    finally:
        stop.set()
        await sweeper


DESCRIPTION = """
Observability and reliability for AI agents: every step an agent takes is recorded as an immutable
event, suspicious runs are flagged by deterministic rules, and failures are investigated from the
recorded evidence.

`contract/API_CONTRACT.md` is the source of truth for every shape here; `docs/API.md` has worked examples.

**Conventions.** JSON keys are snake_case. Ids are opaque prefixed strings (`exe_` + 32 hex).
Timestamps are ISO 8601 UTC with milliseconds and a `Z`. Durations are integer milliseconds. A field
that has no value is `null`, never omitted; unknown tokens and cost are `null`, never `0`. List
endpoints take `limit` (default 50, max 200) and `offset` and return `{items, total, limit, offset}`.
Any payload field over 64 KB is stored as `{"_truncated": true, "original_bytes", "preview"}`.

**Errors.** Every non-2xx response is `{"error": {"code", "message", "details"}}`.

**Authentication (MVP).** Endpoints an SDK writes to need `Authorization: Bearer <GHOSTWATCH_API_KEY>`.
Read endpoints are unauthenticated and meant for localhost.
"""

TAGS = [
    {"name": "health", "description": "Is the backend up, and which investigation provider is in use."},
    {"name": "agents", "description": "Register agents; read their stats and health."},
    {"name": "executions", "description": "Start executions; list and read them."},
    {"name": "events", "description": "Ingestion: the only way an execution's state changes."},
    {"name": "traces", "description": "What happened in an execution: derived steps and the raw event log."},
    {"name": "stats", "description": "Aggregates for the overview."},
    {"name": "anomalies", "description": "What the deterministic rules flagged, with evidence."},
    {"name": "investigations", "description": "Evidence-based reports: facts, hypotheses, recommendations."},
    {
        "name": "replays",
        "description": "Re-run an execution against its recorded calls and compare the result.",
    },
]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Ghostwatch API",
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        lifespan=lifespan,
    )
    # The middleware added last is outermost, so CORS wraps the error middleware and its responses.
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(v1_router, prefix="/api/v1", responses=errors(500))
    _document_errors_in_the_contract_envelope(app)
    return app


def _document_errors_in_the_contract_envelope(app: FastAPI) -> None:
    """Drop FastAPI's default 422 schema from the OpenAPI document.

    FastAPI documents its own validation-error body on every operation that takes a parameter.
    This API never returns that body (see app/errors.py), so the document must not promise it.
    Operations that can fail validation declare the envelope themselves.
    """
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        already_built = app.openapi_schema is not None
        schema = generate()
        if not already_built:
            for operations in schema["paths"].values():
                for operation in operations.values():
                    default = operation["responses"].get("422", {})
                    reference = default.get("content", {}).get("application/json", {}).get("schema", {})
                    if reference.get("$ref", "").endswith("/HTTPValidationError"):
                        del operation["responses"]["422"]
            for name in ("HTTPValidationError", "ValidationError"):
                schema["components"]["schemas"].pop(name, None)
        return schema

    app.openapi = openapi


app = create_app()
