"""Background worker: drains Redis stream -> Postgres + computes hourly rollups.

Run as a separate process:
    python -m app.worker
"""

import asyncio
import json
import logging
import os
import signal
import socket
import sys
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure project root is on sys.path when run as ``python -m app.worker``
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.stream import (
    ack_messages,
    ensure_consumer_group,
    publish_event,
    read_stream_batch,
)
from app.models.event import Event, EventRollupHourly

logger = logging.getLogger(__name__)

# Worker settings
BATCH_SIZE = 200
POLL_INTERVAL_MS = 2000
ROLLUP_INTERVAL_SECONDS = 60  # compute rollups every minute

_shutdown = asyncio.Event()


def _handle_signal(*_):
    logger.info("Shutdown signal received")
    _shutdown.set()


async def _persist_batch(
    session_factory: async_sessionmaker[AsyncSession],
    messages: list[tuple[str, dict[str, str]]],
) -> list[str]:
    """Parse stream messages and bulk-insert into Postgres.

    Returns list of successfully processed message IDs.
    """
    acked_ids: list[str] = []
    events_to_add: list[Event] = []

    for msg_id, fields in messages:
        try:
            data = json.loads(fields["data"])
            project_id = int(fields["project_id"])

            event = Event(
                project_id=project_id,
                event_name=data["event"],
                distinct_id=data.get("distinct_id"),
                properties=data.get("properties"),
                session_id=data.get("session_id"),
                page_url=data.get("page_url"),
                referrer=data.get("referrer"),
                user_agent=data.get("user_agent"),
                ip_hash=data.get("ip_hash"),
                timestamp=datetime.fromisoformat(data["timestamp"])
                if data.get("timestamp")
                else datetime.now(timezone.utc),
            )
            events_to_add.append(event)
            acked_ids.append(msg_id)

            # Publish to pub/sub for live WebSocket delivery
            await publish_event(
                project_id,
                {
                    "event": data["event"],
                    "distinct_id": data.get("distinct_id"),
                    "properties": data.get("properties"),
                    "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    "project_id": project_id,
                },
            )

        except Exception:
            logger.exception("Failed to parse stream message %s", msg_id)
            # Still ack so we don't get stuck in a loop
            acked_ids.append(msg_id)

    if events_to_add:
        async with session_factory() as session:
            session.add_all(events_to_add)
            await session.commit()
        logger.info("Persisted %d events to Postgres", len(events_to_add))

    return acked_ids


async def _compute_rollups(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Compute hourly rollups from raw events.

    Uses a simple approach: for each (project_id, event_name, hour) combo in
    recent events, upsert the aggregated counts into event_rollups_hourly.
    """
    async with session_factory() as session:
        # Aggregate from raw events for the current hour
        now = datetime.now(timezone.utc)
        hour_start = now.replace(minute=0, second=0, microsecond=0)

        stmt = (
            select(
                Event.project_id,
                Event.event_name,
                func.count().label("count"),
                func.count(func.distinct(Event.session_id)).label("unique_sessions"),
                func.count(func.distinct(Event.distinct_id)).label("unique_users"),
            )
            .where(Event.timestamp >= hour_start)
            .group_by(Event.project_id, Event.event_name)
        )

        result = await session.execute(stmt)
        rows = result.all()

        for row in rows:
            # Upsert: try to update existing rollup, else insert
            existing = await session.execute(
                select(EventRollupHourly).where(
                    EventRollupHourly.project_id == row.project_id,
                    EventRollupHourly.event_name == row.event_name,
                    EventRollupHourly.hour == hour_start,
                )
            )
            rollup = existing.scalar_one_or_none()

            if rollup:
                rollup.count = row.count  # type: ignore[assignment]
                rollup.unique_sessions = row.unique_sessions
                rollup.unique_users = row.unique_users
            else:
                rollup = EventRollupHourly(
                    project_id=row.project_id,
                    event_name=row.event_name,
                    hour=hour_start,
                    count=row.count,
                    unique_sessions=row.unique_sessions,
                    unique_users=row.unique_users,
                )
                session.add(rollup)

        await session.commit()

        if rows:
            logger.info("Rolled up %d (project, event) combos for %s", len(rows), hour_start)


async def run_worker() -> None:
    """Main worker loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    logger.info("Starting event stream worker")

    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    consumer_name = f"worker-{socket.gethostname()}-{os.getpid()}"

    await ensure_consumer_group()

    last_rollup = 0.0

    while not _shutdown.is_set():
        messages = await read_stream_batch(
            consumer_name=consumer_name,
            count=BATCH_SIZE,
            block_ms=POLL_INTERVAL_MS,
        )

        if messages:
            acked = await _persist_batch(session_factory, messages)
            await ack_messages(acked)

        # Periodic rollup computation
        now_ts = asyncio.get_event_loop().time()
        if now_ts - last_rollup >= ROLLUP_INTERVAL_SECONDS:
            try:
                await _compute_rollups(session_factory)
            except Exception:
                logger.exception("Rollup computation failed")
            last_rollup = now_ts

    await engine.dispose()
    logger.info("Worker shut down cleanly")


if __name__ == "__main__":
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)
    asyncio.run(run_worker())
