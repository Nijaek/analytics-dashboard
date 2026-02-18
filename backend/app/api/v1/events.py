import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_by_api_key
from app.core.stream import push_event_batch_to_stream
from app.db.session import get_db
from app.models.project import Project
from app.schemas.event import EventIngestRequest, EventIngestResponse
from app.services.event_service import EventService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ingest", response_model=EventIngestResponse)
async def ingest_events(
    request: Request,
    data: EventIngestRequest,
    project: Project = Depends(get_project_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a batch of events. Authenticated via X-API-Key header.

    Attempts to push events to a Redis stream for async processing.
    Falls back to direct Postgres writes if Redis is unavailable.
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    ip_hash = EventService.hash_ip(ip_address) if ip_address else None

    # Build event data for the entire batch
    events_data = []
    for event_in in data.events:
        events_data.append(
            {
                "event": event_in.event,
                "distinct_id": event_in.distinct_id,
                "properties": event_in.properties,
                "session_id": event_in.session_id,
                "page_url": event_in.page_url,
                "referrer": event_in.referrer,
                "user_agent": user_agent,
                "ip_hash": ip_hash,
                "timestamp": (event_in.timestamp or datetime.now(timezone.utc)).isoformat(),
            }
        )

    # Try atomic Redis pipeline — all-or-nothing
    # Stream operations use their own Redis connection (not DI) so the worker
    # and tests can manage stream availability independently.
    msg_ids = await push_event_batch_to_stream(project.id, events_data)
    if msg_ids is not None:
        return EventIngestResponse(accepted=len(msg_ids))

    # Pipeline failed entirely — safe to fall back to Postgres (no duplicates)
    logger.info("Redis stream unavailable, falling back to direct DB writes")
    service = EventService(db)
    count = await service.ingest_batch(
        project_id=project.id,
        events=data.events,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return EventIngestResponse(accepted=count)
