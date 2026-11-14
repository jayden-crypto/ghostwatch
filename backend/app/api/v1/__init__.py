from fastapi import APIRouter

from app.api.v1 import agents, events, executions, health, stats, traces

router = APIRouter()
router.include_router(health.router)
router.include_router(agents.router)
router.include_router(executions.router)
router.include_router(events.router)
router.include_router(traces.router)
router.include_router(stats.router)
