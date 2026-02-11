import logging
from collections import defaultdict
from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.schemas.analytics import (
    OverviewMetrics,
    SessionSummary,
    TimeseriesPoint,
    TopEvent,
    UserSummary,
)

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for analytics queries."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_overview(
        self, project_id: int, start: datetime, end: datetime
    ) -> OverviewMetrics:
        """Get overview metrics for a project within a date range."""
        base = select(Event).where(
            Event.project_id == project_id,
            Event.timestamp >= start,
            Event.timestamp <= end,
        )

        total_result = await self.db.execute(select(func.count()).select_from(base.subquery()))
        total_events = total_result.scalar_one()

        session_result = await self.db.execute(
            select(func.count(distinct(Event.session_id))).where(
                Event.project_id == project_id,
                Event.timestamp >= start,
                Event.timestamp <= end,
                Event.session_id.isnot(None),
            )
        )
        unique_sessions = session_result.scalar_one()

        user_result = await self.db.execute(
            select(func.count(distinct(Event.distinct_id))).where(
                Event.project_id == project_id,
                Event.timestamp >= start,
                Event.timestamp <= end,
                Event.distinct_id.isnot(None),
            )
        )
        unique_users = user_result.scalar_one()

        top_result = await self.db.execute(
            select(Event.event_name, func.count().label("cnt"))
            .where(
                Event.project_id == project_id,
                Event.timestamp >= start,
                Event.timestamp <= end,
            )
            .group_by(Event.event_name)
            .order_by(func.count().desc())
            .limit(1)
        )
        top_row = top_result.first()
        top_event = top_row[0] if top_row else None

        return OverviewMetrics(
            total_events=total_events,
            unique_sessions=unique_sessions,
            unique_users=unique_users,
            top_event=top_event,
            period_start=start,
            period_end=end,
        )

    async def get_timeseries(
        self,
        project_id: int,
        start: datetime,
        end: datetime,
        granularity: str = "hourly",
    ) -> list[TimeseriesPoint]:
        """Get event counts over time."""
        result = await self.db.execute(
            select(Event.timestamp, func.count().label("cnt"))
            .where(
                Event.project_id == project_id,
                Event.timestamp >= start,
                Event.timestamp <= end,
            )
            .group_by(Event.timestamp)
            .order_by(Event.timestamp)
        )
        rows = result.all()

        # Aggregate by hour or day in Python for SQLite test compatibility
        buckets: dict[datetime, int] = defaultdict(int)
        for row in rows:
            ts = row[0]
            if granularity == "daily":
                key = ts.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                key = ts.replace(minute=0, second=0, microsecond=0)
            buckets[key] += row[1]

        return [TimeseriesPoint(timestamp=k, count=v) for k, v in sorted(buckets.items())]

    async def get_top_events(
        self, project_id: int, start: datetime, end: datetime, limit: int = 10
    ) -> list[TopEvent]:
        """Get top events by count."""
        result = await self.db.execute(
            select(
                Event.event_name,
                func.count().label("cnt"),
                func.count(distinct(Event.session_id)).label("sessions"),
                func.count(distinct(Event.distinct_id)).label("users"),
            )
            .where(
                Event.project_id == project_id,
                Event.timestamp >= start,
                Event.timestamp <= end,
            )
            .group_by(Event.event_name)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [
            TopEvent(
                event_name=row[0],
                count=row[1],
                unique_sessions=row[2],
                unique_users=row[3],
            )
            for row in result.all()
        ]

    async def get_sessions(
        self,
        project_id: int,
        start: datetime,
        end: datetime,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SessionSummary], int]:
        """Get session analytics."""
        base = (
            select(
                Event.session_id,
                func.count().label("event_count"),
                func.min(Event.timestamp).label("first_seen"),
                func.max(Event.timestamp).label("last_seen"),
                func.max(Event.distinct_id).label("distinct_id"),
            )
            .where(
                Event.project_id == project_id,
                Event.timestamp >= start,
                Event.timestamp <= end,
                Event.session_id.isnot(None),
            )
            .group_by(Event.session_id)
            .order_by(func.max(Event.timestamp).desc())
        )

        count_result = await self.db.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar_one()

        result = await self.db.execute(base.limit(limit).offset(offset))
        return [
            SessionSummary(
                session_id=row[0],
                event_count=row[1],
                first_seen=row[2],
                last_seen=row[3],
                distinct_id=row[4],
            )
            for row in result.all()
        ], total

    async def get_users(
        self,
        project_id: int,
        start: datetime,
        end: datetime,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[UserSummary], int]:
        """Get identified user analytics."""
        base = (
            select(
                Event.distinct_id,
                func.count().label("event_count"),
                func.count(distinct(Event.session_id)).label("session_count"),
                func.min(Event.timestamp).label("first_seen"),
                func.max(Event.timestamp).label("last_seen"),
            )
            .where(
                Event.project_id == project_id,
                Event.timestamp >= start,
                Event.timestamp <= end,
                Event.distinct_id.isnot(None),
            )
            .group_by(Event.distinct_id)
            .order_by(func.count().desc())
        )

        count_result = await self.db.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar_one()

        result = await self.db.execute(base.limit(limit).offset(offset))
        return [
            UserSummary(
                distinct_id=row[0],
                event_count=row[1],
                session_count=row[2],
                first_seen=row[3],
                last_seen=row[4],
            )
            for row in result.all()
        ], total
