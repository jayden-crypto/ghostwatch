import logging

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.api.deps import SessionDep, SettingsDep
from app.schemas.health import Health

logger = logging.getLogger("ghostwatch")
router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health, summary="Backend, database and LLM provider status")
def get_health(session: SessionDep, settings: SettingsDep) -> Health:
    try:
        session.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError as exc:
        logger.warning("Health check could not reach the database: %s", type(exc).__name__)
        database = "error"
    return Health(
        status="ok",
        version=__version__,
        database=database,
        llm_provider=settings.llm_provider,
        llm_configured=settings.llm_configured,
        llm_model=settings.llm_model_in_use,
    )
