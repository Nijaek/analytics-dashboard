import logging
from datetime import datetime, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, EventRollupHourly
from app.schemas.analytics import (
    OverviewMetrics,
    SessionSummary,
    TimeseriesPoint,
    TopEvent,
    UserSummary,
)

logger = logging.getLogger(__name__)


def _current_hour_start() -> datetime:
    """Return the start of the current UTC hour."""
    now = datetime.now(timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0)


class AnalyticsService:
    """Service for analytics queries."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_overview(
        self, project_id: int, start: datetime, end: datetime
    ) -> OverviewMetrics:
        """Get overview metrics for a project within a date range.

        Uses pre-aggregated rollup table for completed hours and falls back
        to raw events for the current (incomplete) hour only.
        """
        hour_start = _current_hour_start()

        # --- Rollup portion: completed hours within [start, hour_start) ---
        rollup_total = 0
        rollup_sessions = 0
        rollup_users = 0
        rollup_event_counts: dict[str, int] = {}

        if start < hour_start:
            rollup_end = min(end, hour_start)
            r_total = await self.db.execute(
                select(func.coalesce(func.sum(EventRollupHourly.count), 0)).where(
                    EventRollupHourly.project_id == project_id,
                    EventRollupHourly.hour >= start,
                    EventRollupHourly.hour < rollup_end,
                )
            )
            rollup_total = r_total.scalar_one()

            r_sessions = await self.db.execute(
                select(func.coalesce(func.sum(EventRollupHourly.unique_sessions), 0)).where(
                    EventRollupHourly.project_id == project_id,
                    EventRollupHourly.hour >= start,
                    EventRollupHourly.hour < rollup_end,
                )
            )
            rollup_sessions = r_sessions.scalar_one()

            r_users = await self.db.execute(
                select(func.coalesce(func.sum(EventRollupHourly.unique_users), 0)).where(
                    EventRollupHourly.project_id == project_id,
                    EventRollupHourly.hour >= start,
                    EventRollupHourly.hour < rollup_end,
                )
            )
            rollup_users = r_users.scalar_one()

            r_top = await self.db.execute(
                select(
                    EventRollupHourly.event_name,
                    func.sum(EventRollupHourly.count).label("cnt"),
                )
                .where(
                    EventRollupHourly.project_id == project_id,
                    EventRollupHourly.hour >= start,
                    EventRollupHourly.hour < rollup_end,
                )
                .group_by(EventRollupHourly.event_name)
            )
            for row in r_top.all():
                rollup_event_counts[row[0]] = row[1]

        # --- Raw portion: current incomplete hour [hour_start, end] ---
        raw_total = 0
        raw_sessions = 0
        raw_users = 0
        raw_event_counts: dict[str, int] = {}

        if end >= hour_start:
            raw_start = max(start, hour_start)
            base = select(Event).where(
                Event.project_id == project_id,
                Event.timestamp >= raw_start,
                Event.timestamp <= end,
            )
            rt = await self.db.execute(select(func.count()).select_from(base.subquery()))
            raw_total = rt.scalar_one()

            rs = await self.db.execute(
                select(func.count(distinct(Event.session_id))).where(
                    Event.project_id == project_id,
                    Event.timestamp >= raw_start,
                    Event.timestamp <= end,
                    Event.session_id.isnot(None),
                )
            )
            raw_sessions = rs.scalar_one()

            ru = await self.db.execute(
                select(func.count(distinct(Event.distinct_id))).where(
                    Event.project_id == project_id,
                    Event.timestamp >= raw_start,
                    Event.timestamp <= end,
                    Event.distinct_id.isnot(None),
                )
            )
            raw_users = ru.scalar_one()

            re_top = await self.db.execute(
                select(Event.event_name, func.count().label("cnt"))
                .where(
                    Event.project_id == project_id,
                    Event.timestamp >= raw_start,
                    Event.timestamp <= end,
                )
                .group_by(Event.event_name)
            )
            for row in re_top.all():
                raw_event_counts[row[0]] = row[1]

        # --- Combine ---
        total_events = rollup_total + raw_total
        unique_sessions = rollup_sessions + raw_sessions
        unique_users = rollup_users + raw_users

        combined_counts: dict[str, int] = {}
        for name, cnt in rollup_event_counts.items():
            combined_counts[name] = combined_counts.get(name, 0) + cnt
        for name, cnt in raw_event_counts.items():
            combined_counts[name] = combined_counts.get(name, 0) + cnt

        top_event = (
            max(combined_counts, key=combined_counts.get)  # type: ignore[arg-type]
            if combined_counts
            else None
        )

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
        """Get event counts over time.

        Uses rollup table for completed hours and raw events for the
        current incomplete hour, then merges the results.
        """
        hour_start = _current_hour_start()
        points: dict[str, int] = {}  # ISO timestamp string -> count

        # --- Rollup portion: completed hours ---
        if start < hour_start:
            rollup_end = min(end, hour_start)

            if granularity == "daily":
                bind = self.db.get_bind()
                is_sqlite = bind.dialect.name == "sqlite"
                if is_sqlite:
                    day_expr = func.strftime("%Y-%m-%d 00:00:00", EventRollupHourly.hour)
                else:
                    day_expr = func.date_trunc("day", EventRollupHourly.hour)

                result = await self.db.execute(
                    select(
                        day_expr.label("bucket"),
                        func.sum(EventRollupHourly.count).label("cnt"),
                    )
                    .where(
                        EventRollupHourly.project_id == project_id,
                        EventRollupHourly.hour >= start,
                        EventRollupHourly.hour < rollup_end,
                    )
                    .group_by(day_expr)
                )
            else:
                result = await self.db.execute(
                    select(
                        EventRollupHourly.hour.label("bucket"),
                        func.sum(EventRollupHourly.count).label("cnt"),
                    )
                    .where(
                        EventRollupHourly.project_id == project_id,
                        EventRollupHourly.hour >= start,
                        EventRollupHourly.hour < rollup_end,
                    )
                    .group_by(EventRollupHourly.hour)
                )

            for row in result.all():
                ts = row[0] if isinstance(row[0], datetime) else datetime.fromisoformat(row[0])
                key = ts.isoformat()
                points[key] = points.get(key, 0) + row[1]

        # --- Raw portion: current incomplete hour ---
        if end >= hour_start:
            raw_start = max(start, hour_start)
            bind = self.db.get_bind()
            is_sqlite = bind.dialect.name == "sqlite"

            if is_sqlite:
                if granularity == "daily":
                    trunc_expr = func.strftime("%Y-%m-%d 00:00:00", Event.timestamp)
                else:
                    trunc_expr = func.strftime("%Y-%m-%d %H:00:00", Event.timestamp)
            else:
                trunc_unit = "day" if granularity == "daily" else "hour"
                trunc_expr = func.date_trunc(trunc_unit, Event.timestamp)

            result = await self.db.execute(
                select(trunc_expr.label("bucket"), func.count().label("cnt"))
                .where(
                    Event.project_id == project_id,
                    Event.timestamp >= raw_start,
                    Event.timestamp <= end,
                )
                .group_by(trunc_expr)
            )

            for row in result.all():
                ts = row[0] if isinstance(row[0], datetime) else datetime.fromisoformat(row[0])
                key = ts.isoformat()
                points[key] = points.get(key, 0) + row[1]

        sorted_keys = sorted(points.keys())
        return [
            TimeseriesPoint(
                timestamp=datetime.fromisoformat(k),
                count=points[k],
            )
            for k in sorted_keys
        ]

    async def get_top_events(
        self, project_id: int, start: datetime, end: datetime, limit: int = 10
    ) -> list[TopEvent]:
        """Get top events by count.

        Combines rollup data for completed hours with raw events for
        the current incomplete hour.
        """
        hour_start = _current_hour_start()
        combined: dict[str, dict[str, int]] = {}

        # --- Rollup portion ---
        if start < hour_start:
            rollup_end = min(end, hour_start)
            result = await self.db.execute(
                select(
                    EventRollupHourly.event_name,
                    func.sum(EventRollupHourly.count).label("cnt"),
                    func.sum(EventRollupHourly.unique_sessions).label("sessions"),
                    func.sum(EventRollupHourly.unique_users).label("users"),
                )
                .where(
                    EventRollupHourly.project_id == project_id,
                    EventRollupHourly.hour >= start,
                    EventRollupHourly.hour < rollup_end,
                )
                .group_by(EventRollupHourly.event_name)
            )
            for row in result.all():
                combined[row[0]] = {
                    "count": row[1],
                    "sessions": row[2],
                    "users": row[3],
                }

        # --- Raw portion ---
        if end >= hour_start:
            raw_start = max(start, hour_start)
            result = await self.db.execute(
                select(
                    Event.event_name,
                    func.count().label("cnt"),
                    func.count(distinct(Event.session_id)).label("sessions"),
                    func.count(distinct(Event.distinct_id)).label("users"),
                )
                .where(
                    Event.project_id == project_id,
                    Event.timestamp >= raw_start,
                    Event.timestamp <= end,
                )
                .group_by(Event.event_name)
            )
            for row in result.all():
                if row[0] in combined:
                    combined[row[0]]["count"] += row[1]
                    combined[row[0]]["sessions"] += row[2]
                    combined[row[0]]["users"] += row[3]
                else:
                    combined[row[0]] = {
                        "count": row[1],
                        "sessions": row[2],
                        "users": row[3],
                    }

        sorted_events = sorted(combined.items(), key=lambda x: x[1]["count"], reverse=True)
        return [
            TopEvent(
                event_name=name,
                count=data["count"],
                unique_sessions=data["sessions"],
                unique_users=data["users"],
            )
            for name, data in sorted_events[:limit]
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
