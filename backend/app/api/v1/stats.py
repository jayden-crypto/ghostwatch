from fastapi import APIRouter

from app.api.deps import SessionDep
from app.api.responses import errors
from app.schemas.stats import Bucket, StatsOverview, StatsTimeseries, Window
from app.services import stats as service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get(
    "/overview", response_model=StatsOverview, responses=errors(422), summary="Totals for the overview page"
)
def get_overview(session: SessionDep, window: Window = "7d") -> StatsOverview:
    """Counts of executions started inside the window, by status.

    A window is whole UTC buckets ending with the current one: `24h` is this hour and the 23 before
    it, `7d` is today and the 6 days before it. `success_rate` and `avg_duration_ms` are null when
    nothing has finished. `total_agents` and `open_anomalies` are current totals, not windowed.
    """
    return service.get_overview(session, window)


@router.get(
    "/timeseries",
    response_model=StatsTimeseries,
    responses=errors(404, 422),
    summary="Executions per bucket, zero-filled",
)
def get_timeseries(
    session: SessionDep, window: Window = "7d", bucket: Bucket | None = None, agent_id: str | None = None
) -> StatsTimeseries:
    """One point per bucket, oldest first, with zeros where nothing ran, so charts have no gaps.

    `bucket` defaults to `hour` for `24h` and `day` otherwise. With the default bucket the points
    add up to the overview's totals for the same window. Running executions are not in the points.
    """
    return service.get_timeseries(session, window, bucket, agent_id)
