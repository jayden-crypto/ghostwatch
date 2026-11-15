from fastapi import APIRouter

from app.api.v1 import (
    agents,
    anomalies,
    events,
    executions,
    health,
    investigations,
    replays,
    stats,
    traces,
)

router = APIRouter()
router.include_router(health.router)
router.include_router(agents.router)
router.include_router(executions.router)
router.include_router(events.router)
router.include_router(traces.router)
router.include_router(stats.router)
router.include_router(anomalies.router)
router.include_router(investigations.router)
router.include_router(replays.router)
