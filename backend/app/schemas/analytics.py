from datetime import datetime

from pydantic import BaseModel


class OverviewMetrics(BaseModel):
    """Summary analytics overview."""

    total_events: int
    unique_sessions: int
    unique_users: int
    top_event: str | None
    period_start: datetime
    period_end: datetime


class TimeseriesPoint(BaseModel):
    """Single point in a timeseries."""

    timestamp: datetime
    count: int


class TimeseriesResponse(BaseModel):
    """Timeseries analytics response."""

    data: list[TimeseriesPoint]
    granularity: str  # "hourly" or "daily"


class TopEvent(BaseModel):
    """Top event by count."""

    event_name: str
    count: int
    unique_sessions: int
    unique_users: int


class TopEventsResponse(BaseModel):
    """Top events response."""

    data: list[TopEvent]


class SessionSummary(BaseModel):
    """Session analytics summary."""

    session_id: str
    event_count: int
    first_seen: datetime
    last_seen: datetime
    distinct_id: str | None


class SessionsResponse(BaseModel):
    """Sessions analytics response."""

    data: list[SessionSummary]
    total: int


class UserSummary(BaseModel):
    """Identified user analytics summary."""

    distinct_id: str
    event_count: int
    session_count: int
    first_seen: datetime
    last_seen: datetime


class UsersResponse(BaseModel):
    """Users analytics response."""

    data: list[UserSummary]
    total: int
