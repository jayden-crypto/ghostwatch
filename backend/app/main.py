"""Application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
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


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Ghostwatch API",
        version=__version__,
        description="Observability and reliability for AI agents. See contract/API_CONTRACT.md.",
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
    app.include_router(v1_router, prefix="/api/v1")
    return app


app = create_app()
