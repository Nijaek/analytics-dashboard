import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.schemas.event import EventIn

logger = logging.getLogger(__name__)


class EventService:
    """Service for event ingestion and querying."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def hash_ip(ip: str) -> str:
        """Hash an IP address with SHA-256 for privacy."""
        return hashlib.sha256(ip.encode()).hexdigest()

    async def ingest_batch(
        self,
        project_id: int,
        events: list[EventIn],
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> int:
        """Ingest a batch of events (direct-to-Postgres for Phase 1)."""
        ip_hash = self.hash_ip(ip_address) if ip_address else None
        count = 0

        for event_in in events:
            event = Event(
                project_id=project_id,
                event_name=event_in.event,
                distinct_id=event_in.distinct_id,
                properties=event_in.properties,
                session_id=event_in.session_id,
                page_url=event_in.page_url,
                referrer=event_in.referrer,
                user_agent=user_agent,
                ip_hash=ip_hash,
                timestamp=event_in.timestamp or datetime.now(timezone.utc),
            )
            self.db.add(event)
            count += 1

        await self.db.flush()
        return count
