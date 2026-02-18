"""Redis client for token revocation and caching."""

import logging

import redis.asyncio as redis
from fastapi import Request
from redis.asyncio import ConnectionPool
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)

# Connection pool settings
SOCKET_TIMEOUT = 5.0  # seconds
SOCKET_CONNECT_TIMEOUT = 5.0  # seconds
RETRY_ON_TIMEOUT = True
MAX_CONNECTIONS = 10

# Module-level globals kept only for standalone / worker contexts
redis_client: redis.Redis | None = None
_connection_pool: ConnectionPool | None = None


def create_redis_client() -> redis.Redis:
    """Create a new Redis client with a dedicated connection pool.

    Used by the FastAPI lifespan to attach a managed client to ``app.state``.
    The caller is responsible for closing the returned client on shutdown.
    """
    pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_timeout=SOCKET_TIMEOUT,
        socket_connect_timeout=SOCKET_CONNECT_TIMEOUT,
        retry_on_timeout=RETRY_ON_TIMEOUT,
        max_connections=MAX_CONNECTIONS,
    )
    return redis.Redis(connection_pool=pool)


async def get_redis() -> redis.Redis:
    """Get or create a module-level Redis client (for worker / non-DI contexts)."""
    global redis_client, _connection_pool
    if redis_client is None:
        _connection_pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=SOCKET_TIMEOUT,
            socket_connect_timeout=SOCKET_CONNECT_TIMEOUT,
            retry_on_timeout=RETRY_ON_TIMEOUT,
            max_connections=MAX_CONNECTIONS,
        )
        redis_client = redis.Redis(connection_pool=_connection_pool)
    return redis_client


async def get_redis_dep(request: Request) -> redis.Redis:
    """FastAPI dependency — returns the Redis client from ``app.state``."""
    return request.app.state.redis  # type: ignore[no-any-return]


async def close_redis() -> None:
    """Close the module-level Redis connection and pool."""
    global redis_client, _connection_pool
    if redis_client:
        await redis_client.close()
        redis_client = None
    if _connection_pool:
        await _connection_pool.disconnect()
        _connection_pool = None


async def safe_redis_exists(
    key: str,
    *,
    client: redis.Redis | None = None,
    fail_closed: bool = True,
) -> bool:
    """Check if key exists with configurable failure behavior.

    Args:
        key: Redis key to check.
        client: Redis client to use. Falls back to ``get_redis()`` when *None*.
        fail_closed: If True, treat errors as "key doesn't exist" (safer for
            revocation checks where missing key = revoked token).

    Returns:
        True if key exists, False otherwise.

    Raises:
        ServiceUnavailableError: If fail_closed is False and Redis is unavailable.
    """
    try:
        r = client or await get_redis()
        return bool(await r.exists(key))
    except RedisError as e:
        logger.error(f"Redis EXISTS failed for {key}: {e}")
        if fail_closed:
            return False
        raise ServiceUnavailableError("Unable to verify token status") from None


async def safe_redis_setex(
    key: str,
    ttl: int,
    value: str,
    *,
    client: redis.Redis | None = None,
    raise_on_error: bool = True,
) -> bool:
    """Set key with expiration, with error handling.

    Args:
        key: Redis key to set.
        ttl: Time to live in seconds.
        value: Value to store.
        client: Redis client to use. Falls back to ``get_redis()`` when *None*.
        raise_on_error: If True, raise ServiceUnavailableError on failure.

    Returns:
        True if successful, False otherwise.

    Raises:
        ServiceUnavailableError: If raise_on_error is True and Redis is unavailable.
    """
    try:
        r = client or await get_redis()
        await r.setex(key, ttl, value)
        return True
    except RedisError as e:
        logger.error(f"Redis SETEX failed for {key}: {e}")
        if raise_on_error:
            raise ServiceUnavailableError("Unable to store token - please try again") from None
        return False


async def safe_redis_delete(
    *keys: str,
    client: redis.Redis | None = None,
    raise_on_error: bool = False,
) -> int:
    """Delete keys with error handling.

    Args:
        keys: Redis keys to delete.
        client: Redis client to use. Falls back to ``get_redis()`` when *None*.
        raise_on_error: If True, raise ServiceUnavailableError on failure.

    Returns:
        Number of keys deleted.

    Raises:
        ServiceUnavailableError: If raise_on_error is True and Redis is unavailable.
    """
    try:
        r = client or await get_redis()
        result: int = await r.delete(*keys)
        return result
    except RedisError as e:
        logger.warning(f"Redis DELETE failed for {keys}: {e}")
        if raise_on_error:
            raise ServiceUnavailableError("Unable to revoke token") from None
        return 0
