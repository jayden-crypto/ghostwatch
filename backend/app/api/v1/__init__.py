from fastapi import APIRouter

from app.api.v1 import agents, health

router = APIRouter()
router.include_router(health.router)
router.include_router(agents.router)
