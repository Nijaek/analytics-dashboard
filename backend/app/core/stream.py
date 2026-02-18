"""Redis stream and pub/sub helpers for event pipeline."""

import json
import logging
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

# Stream / consumer-group constants
STREAM_KEY = "events:ingest"
GROUP_NAME = "event_workers"
PUBSUB_PREFIX = "events:live:"  # per-project channel: events:live:{project_id}


async def push_event_to_stream(
    project_id: int,
    event_data: dict[str, Any],
    *,
    redis: Redis | None = None,
) -> str | None:
    """XADD an event to the ingest stream.

    Returns the stream message ID on success, or None if Redis is unavailable.
    """
    try:
        r = redis or await get_redis()
        payload = {
            "project_id": str(project_id),
            "data": json.dumps(event_data, default=str),
        }
        msg_id: str = await r.xadd(STREAM_KEY, payload)  # type: ignore[arg-type]
        return msg_id
    except (RedisError, Exception) as exc:
        logger.warning("XADD to %s failed: %s", STREAM_KEY, exc)
        return None


async def push_event_batch_to_stream(
    project_id: int,
    events_data: list[dict[str, Any]],
    *,
    redis: Redis | None = None,
) -> list[str] | None:
    """Atomically XADD a batch of events using a Redis pipeline.

    Returns list of stream message IDs on success, or None if Redis
    is unavailable. Because a pipeline is all-or-nothing at the network
    level, a failure means NO events are in the stream, making a
    Postgres fallback safe with no duplicates.
    """
    if not events_data:
        return []
    try:
        r = redis or await get_redis()
        pipe = r.pipeline(transaction=False)
        for event_data in events_data:
            payload = {
                "project_id": str(project_id),
                "data": json.dumps(event_data, default=str),
            }
            pipe.xadd(STREAM_KEY, payload)  # type: ignore[arg-type]
        results = await pipe.execute()
        return results  # type: ignore[no-any-return]
    except (RedisError, Exception) as exc:
        logger.warning("Pipeline XADD to %s failed: %s", STREAM_KEY, exc)
        return None


async def ensure_consumer_group(*, redis: Redis | None = None) -> None:
    """Create the consumer group if it doesn't already exist."""
    try:
        r = redis or await get_redis()
        await r.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        logger.info("Created consumer group %s on %s", GROUP_NAME, STREAM_KEY)
    except RedisError as exc:
        # BUSYGROUP means the group already exists — that's fine
        if "BUSYGROUP" in str(exc):
            pass
        else:
            logger.warning("xgroup_create failed: %s", exc)


async def read_stream_batch(
    consumer_name: str,
    count: int = 100,
    block_ms: int = 2000,
    *,
    redis: Redis | None = None,
) -> list[tuple[str, dict[str, str]]]:
    """XREADGROUP: read pending messages from the stream.

    Returns a list of (message_id, fields) tuples.
    """
    try:
        r = redis or await get_redis()
        result = await r.xreadgroup(
            GROUP_NAME,
            consumer_name,
            {STREAM_KEY: ">"},
            count=count,
            block=block_ms,
        )
        if not result:
            return []
        # result is [[stream_name, [(msg_id, fields), ...]]]
        messages: list[tuple[str, dict[str, str]]] = result[0][1]
        return messages
    except (RedisError, Exception) as exc:
        logger.warning("XREADGROUP failed: %s", exc)
        return []


async def ack_messages(message_ids: list[str], *, redis: Redis | None = None) -> int:
    """XACK processed messages."""
    if not message_ids:
        return 0
    try:
        r = redis or await get_redis()
        return int(await r.xack(STREAM_KEY, GROUP_NAME, *message_ids))
    except (RedisError, Exception) as exc:
        logger.warning("XACK failed: %s", exc)
        return 0


async def publish_event(
    project_id: int,
    event_data: dict[str, Any],
    *,
    redis: Redis | None = None,
) -> bool:
    """Publish an event to the per-project pub/sub channel."""
    channel = f"{PUBSUB_PREFIX}{project_id}"
    try:
        r = redis or await get_redis()
        await r.publish(channel, json.dumps(event_data, default=str))
        return True
    except (RedisError, Exception) as exc:
        logger.warning("PUBLISH to %s failed: %s", channel, exc)
        return False


async def subscribe_project(
    project_id: int,
    *,
    redis: Redis | None = None,
):
    """Return a Redis pub/sub subscription for a project channel.

    Returns (pubsub_object, channel_name) or (None, None) on failure.
    """
    channel = f"{PUBSUB_PREFIX}{project_id}"
    try:
        r = redis or await get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        return pubsub, channel
    except (RedisError, Exception) as exc:
        logger.warning("SUBSCRIBE to %s failed: %s", channel, exc)
        return None, None
