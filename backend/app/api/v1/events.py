from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_by_api_key
from app.db.session import get_db
from app.models.project import Project
from app.schemas.event import EventIngestRequest, EventIngestResponse
from app.services.event_service import EventService

router = APIRouter()


@router.post("/ingest", response_model=EventIngestResponse)
async def ingest_events(
    request: Request,
    data: EventIngestRequest,
    project: Project = Depends(get_project_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a batch of events. Authenticated via X-API-Key header."""
    service = EventService(db)
    count = await service.ingest_batch(
        project_id=project.id,
        events=data.events,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return EventIngestResponse(accepted=count)
