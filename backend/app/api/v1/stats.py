from fastapi import APIRouter

from app.api.deps import SessionDep
from app.schemas.stats import Bucket, StatsOverview, StatsTimeseries, Window
from app.services import stats as service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", response_model=StatsOverview, summary="Totals for the overview page")
def get_overview(session: SessionDep, window: Window = "7d") -> StatsOverview:
    return service.get_overview(session, window)


@router.get("/timeseries", response_model=StatsTimeseries, summary="Executions per bucket, zero-filled")
def get_timeseries(
    session: SessionDep, window: Window = "7d", bucket: Bucket | None = None, agent_id: str | None = None
) -> StatsTimeseries:
    return service.get_timeseries(session, window, bucket, agent_id)
