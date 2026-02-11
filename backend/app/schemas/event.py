from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventIn(BaseModel):
    """Schema for a single event in ingest payload."""

    event: str = Field(..., min_length=1, max_length=255)
    properties: dict[str, Any] | None = None
    distinct_id: str | None = Field(None, max_length=255)
    session_id: str | None = Field(None, max_length=64)
    page_url: str | None = None
    referrer: str | None = None
    timestamp: datetime | None = None


class EventIngestRequest(BaseModel):
    """Schema for event ingestion — batched."""

    events: list[EventIn] = Field(..., min_length=1, max_length=100)


class EventIngestResponse(BaseModel):
    """Schema for event ingestion response."""

    accepted: int


class EventResponse(BaseModel):
    """Schema for event response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    event_name: str
    distinct_id: str | None
    properties: dict[str, Any] | None
    session_id: str | None
    page_url: str | None
    referrer: str | None
    timestamp: datetime
    created_at: datetime
