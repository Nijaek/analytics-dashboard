"""Redis stream and pub/sub helpers for event pipeline."""

import json
import logging
from typing import Any

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
) -> str | None:
    """XADD an event to the ingest stream.

    Returns the stream message ID on success, or None if Redis is unavailable.
    """
    try:
        r = await get_redis()
        payload = {
            "project_id": str(project_id),
            "data": json.dumps(event_data, default=str),
        }
        msg_id: str = await r.xadd(STREAM_KEY, payload)  # type: ignore[arg-type]
        return msg_id
    except (RedisError, Exception) as exc:
        logger.warning("XADD to %s failed: %s", STREAM_KEY, exc)
        return None


async def ensure_consumer_group() -> None:
    """Create the consumer group if it doesn't already exist."""
    try:
        r = await get_redis()
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
) -> list[tuple[str, dict[str, str]]]:
    """XREADGROUP: read pending messages from the stream.

    Returns a list of (message_id, fields) tuples.
    """
    try:
        r = await get_redis()
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


async def ack_messages(message_ids: list[str]) -> int:
    """XACK processed messages."""
    if not message_ids:
        return 0
    try:
        r = await get_redis()
        return int(await r.xack(STREAM_KEY, GROUP_NAME, *message_ids))
    except (RedisError, Exception) as exc:
        logger.warning("XACK failed: %s", exc)
        return 0


async def publish_event(project_id: int, event_data: dict[str, Any]) -> bool:
    """Publish an event to the per-project pub/sub channel."""
    channel = f"{PUBSUB_PREFIX}{project_id}"
    try:
        r = await get_redis()
        await r.publish(channel, json.dumps(event_data, default=str))
        return True
    except (RedisError, Exception) as exc:
        logger.warning("PUBLISH to %s failed: %s", channel, exc)
        return False


async def subscribe_project(project_id: int):
    """Return a Redis pub/sub subscription for a project channel.

    Returns (pubsub_object, channel_name) or (None, None) on failure.
    """
    channel = f"{PUBSUB_PREFIX}{project_id}"
    try:
        r = await get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        return pubsub, channel
    except (RedisError, Exception) as exc:
        logger.warning("SUBSCRIBE to %s failed: %s", channel, exc)
        return None, None
