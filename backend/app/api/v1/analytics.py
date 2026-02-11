from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.analytics import (
    OverviewMetrics,
    SessionsResponse,
    TimeseriesResponse,
    TopEventsResponse,
    UsersResponse,
)
from app.services.analytics_service import AnalyticsService
from app.services.project_service import ProjectService

router = APIRouter()


def _parse_date_range(
    start: datetime | None, end: datetime | None, period: str = "24h"
) -> tuple[datetime, datetime]:
    """Parse date range from query params or default period."""
    now = datetime.now(timezone.utc)
    if end is None:
        end = now
    if start is None:
        if period == "7d":
            start = now - timedelta(days=7)
        elif period == "30d":
            start = now - timedelta(days=30)
        else:  # 24h default
            start = now - timedelta(hours=24)
    return start, end


@router.get("/{project_id}/overview", response_model=OverviewMetrics)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def get_overview(
    request: Request,
    project_id: int,
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get overview metrics for a project."""
    project_service = ProjectService(db)
    await project_service.get(project_id=project_id, user_id=current_user.id)

    start_dt, end_dt = _parse_date_range(start, end, period)
    service = AnalyticsService(db)
    return await service.get_overview(project_id, start_dt, end_dt)


@router.get("/{project_id}/timeseries", response_model=TimeseriesResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def get_timeseries(
    request: Request,
    project_id: int,
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    granularity: str = Query("hourly", pattern="^(hourly|daily)$"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get events over time for a project."""
    project_service = ProjectService(db)
    await project_service.get(project_id=project_id, user_id=current_user.id)

    start_dt, end_dt = _parse_date_range(start, end, period)
    service = AnalyticsService(db)
    data = await service.get_timeseries(project_id, start_dt, end_dt, granularity)
    return TimeseriesResponse(data=data, granularity=granularity)


@router.get("/{project_id}/top-events", response_model=TopEventsResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def get_top_events(
    request: Request,
    project_id: int,
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    limit: int = Query(10, ge=1, le=50),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get top event names by count."""
    project_service = ProjectService(db)
    await project_service.get(project_id=project_id, user_id=current_user.id)

    start_dt, end_dt = _parse_date_range(start, end, period)
    service = AnalyticsService(db)
    data = await service.get_top_events(project_id, start_dt, end_dt, limit)
    return TopEventsResponse(data=data)


@router.get("/{project_id}/sessions", response_model=SessionsResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def get_sessions(
    request: Request,
    project_id: int,
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get session analytics."""
    project_service = ProjectService(db)
    await project_service.get(project_id=project_id, user_id=current_user.id)

    start_dt, end_dt = _parse_date_range(start, end, period)
    service = AnalyticsService(db)
    data, total = await service.get_sessions(project_id, start_dt, end_dt, limit, offset)
    return SessionsResponse(data=data, total=total)


@router.get("/{project_id}/users", response_model=UsersResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def get_users(
    request: Request,
    project_id: int,
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get identified user analytics."""
    project_service = ProjectService(db)
    await project_service.get(project_id=project_id, user_id=current_user.id)

    start_dt, end_dt = _parse_date_range(start, end, period)
    service = AnalyticsService(db)
    data, total = await service.get_users(project_id, start_dt, end_dt, limit, offset)
    return UsersResponse(data=data, total=total)
