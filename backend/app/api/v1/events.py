import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_by_api_key
from app.core.stream import push_event_to_stream
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

    # Try Redis stream path first
    stream_count = 0
    fallback_needed = False

    for event_in in data.events:
        event_data = {
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
        msg_id = await push_event_to_stream(project.id, event_data)
        if msg_id is not None:
            stream_count += 1
        else:
            # Redis unavailable — switch to direct DB fallback for entire batch
            fallback_needed = True
            break

    if fallback_needed:
        # Fall back to direct Postgres writes (original path)
        logger.info("Redis stream unavailable, falling back to direct DB writes")
        service = EventService(db)
        count = await service.ingest_batch(
            project_id=project.id,
            events=data.events,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return EventIngestResponse(accepted=count)

    return EventIngestResponse(accepted=stream_count)
