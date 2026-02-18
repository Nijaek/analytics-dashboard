import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.redis import (
    get_redis,
    safe_redis_delete,
    safe_redis_exists,
    safe_redis_setex,
)

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_token(subject: int, token_type: str, expires_delta: timedelta) -> tuple[str, str]:
    """Create a JWT token with the given subject and expiration.

    Returns:
        tuple[str, str]: (token, jti) - The encoded JWT token and its unique identifier.
    """
    jti = str(uuid.uuid4())
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "type": token_type,
        "jti": jti,
    }
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, jti


def create_access_token(subject: int) -> tuple[str, str]:
    """Create an access token for the given user ID.

    Returns:
        tuple[str, str]: (token, jti)
    """
    return create_token(
        subject=subject,
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(subject: int) -> tuple[str, str]:
    """Create a refresh token for the given user ID.

    Returns:
        tuple[str, str]: (token, jti)
    """
    return create_token(
        subject=subject,
        token_type="refresh",
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT token. Returns None if invalid."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload
    except jwt.PyJWTError:
        return None


async def store_access_token(
    user_id: int,
    jti: str,
    expires_in_seconds: int,
    *,
    redis: Redis | None = None,
) -> None:
    """Store access token JTI in Redis.

    Stores both the token lookup key and a user->token mapping for bulk revocation.

    Raises:
        ServiceUnavailableError: If Redis is unavailable.
    """
    token_key = f"access_token:{jti}"
    await safe_redis_setex(
        token_key, expires_in_seconds, str(user_id), client=redis, raise_on_error=True
    )
    user_token_key = f"user_access_tokens:{user_id}:{jti}"
    await safe_redis_setex(
        user_token_key, expires_in_seconds, "1", client=redis, raise_on_error=True
    )


async def is_access_token_revoked(jti: str, *, redis: Redis | None = None) -> bool:
    """Check if an access token has been revoked.

    A token is considered revoked if it doesn't exist in Redis.
    Uses fail-closed behavior: if Redis is unavailable, treats token as revoked.
    """
    key = f"access_token:{jti}"
    return not await safe_redis_exists(key, client=redis, fail_closed=True)


async def revoke_access_token(jti: str, *, redis: Redis | None = None) -> None:
    """Revoke a single access token.

    Errors are logged but not raised - token will expire naturally if revocation fails.
    """
    try:
        r = redis or await get_redis()
        token_key = f"access_token:{jti}"
        user_id = await r.get(token_key)
        await safe_redis_delete(token_key, client=r)
        if user_id:
            user_token_key = f"user_access_tokens:{user_id}:{jti}"
            await safe_redis_delete(user_token_key, client=r)
    except RedisError as e:
        logger.warning(f"Failed to revoke access token {jti}: {e}")


async def revoke_all_user_access_tokens(user_id: int, *, redis: Redis | None = None) -> None:
    """Revoke all access tokens for a user (e.g., on logout or password change).

    Uses pattern matching to find and delete all access tokens for the user.
    Errors are logged but not raised - tokens will expire naturally if revocation fails.
    """
    try:
        r = redis or await get_redis()
        pattern = f"user_access_tokens:{user_id}:*"
        keys_to_delete: list[str] = []
        async for key in r.scan_iter(pattern):
            keys_to_delete.append(key)
            jti = key.split(":")[-1]
            keys_to_delete.append(f"access_token:{jti}")
        if keys_to_delete:
            await safe_redis_delete(*keys_to_delete, client=r)
    except RedisError as e:
        logger.warning(f"Failed to revoke all access tokens for user {user_id}: {e}")


async def store_refresh_token(
    user_id: int,
    jti: str,
    expires_in_seconds: int,
    *,
    redis: Redis | None = None,
) -> None:
    """Store refresh token JTI in Redis.

    Stores both the token lookup key and a user->token mapping for bulk revocation.

    Raises:
        ServiceUnavailableError: If Redis is unavailable.
    """
    token_key = f"refresh_token:{jti}"
    await safe_redis_setex(
        token_key, expires_in_seconds, str(user_id), client=redis, raise_on_error=True
    )
    user_token_key = f"user_tokens:{user_id}:{jti}"
    await safe_redis_setex(
        user_token_key, expires_in_seconds, "1", client=redis, raise_on_error=True
    )


async def is_token_revoked(jti: str, *, redis: Redis | None = None) -> bool:
    """Check if a refresh token has been revoked.

    A token is considered revoked if it doesn't exist in Redis.
    Uses fail-closed behavior: if Redis is unavailable, treats token as revoked.
    """
    key = f"refresh_token:{jti}"
    return not await safe_redis_exists(key, client=redis, fail_closed=True)


async def revoke_token(jti: str, *, redis: Redis | None = None) -> None:
    """Revoke a single refresh token.

    Errors are logged but not raised - token will expire naturally if revocation fails.
    """
    try:
        r = redis or await get_redis()
        token_key = f"refresh_token:{jti}"
        user_id = await r.get(token_key)
        await safe_redis_delete(token_key, client=r)
        if user_id:
            user_token_key = f"user_tokens:{user_id}:{jti}"
            await safe_redis_delete(user_token_key, client=r)
    except RedisError as e:
        logger.warning(f"Failed to revoke token {jti}: {e}")


# --- Account lockout ---

LOCKOUT_PREFIX = "login_failures:"
MAX_LOGIN_FAILURES = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minutes


async def check_account_locked(email: str, *, redis: Redis | None = None) -> bool:
    """Check if an account is locked due to too many failed login attempts."""
    key = f"{LOCKOUT_PREFIX}{email}"
    try:
        r = redis or await get_redis()
        failures = await r.get(key)
        return failures is not None and int(failures) >= MAX_LOGIN_FAILURES
    except (RedisError, Exception):
        return False  # Fail-open: don't lock out if Redis is down


async def record_failed_login(email: str, *, redis: Redis | None = None) -> None:
    """Increment failed login counter with TTL."""
    key = f"{LOCKOUT_PREFIX}{email}"
    try:
        r = redis or await get_redis()
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, LOCKOUT_SECONDS)
        await pipe.execute()
    except (RedisError, Exception) as exc:
        logger.warning("Failed to record login failure for %s: %s", email, exc)


async def clear_failed_logins(email: str, *, redis: Redis | None = None) -> None:
    """Reset failed login counter on successful login."""
    key = f"{LOCKOUT_PREFIX}{email}"
    await safe_redis_delete(key, client=redis)


# --- WebSocket ticket auth ---

WS_TICKET_PREFIX = "ws_ticket:"
WS_TICKET_TTL = 30  # seconds


async def create_ws_ticket(user_id: int, *, redis: Redis | None = None) -> str:
    """Create a short-lived single-use WebSocket ticket.

    Returns a unique ticket string stored in Redis with 30s TTL.
    """
    ticket = str(uuid.uuid4())
    key = f"{WS_TICKET_PREFIX}{ticket}"
    r = redis or await get_redis()
    await r.setex(key, WS_TICKET_TTL, str(user_id))
    return ticket


async def validate_ws_ticket(ticket: str, *, redis: Redis | None = None) -> int | None:
    """Validate and consume a WebSocket ticket (single-use).

    Returns the user_id if valid, None otherwise.
    Deletes the ticket after use (single-use).
    """
    key = f"{WS_TICKET_PREFIX}{ticket}"
    r = redis or await get_redis()
    user_id_str = await r.get(key)
    if user_id_str is None:
        return None
    # Delete immediately — single-use
    await r.delete(key)
    return int(user_id_str)


async def revoke_all_user_tokens(user_id: int, *, redis: Redis | None = None) -> None:
    """Revoke all tokens (access and refresh) for a user (e.g., on password change).

    Uses pattern matching to find and delete all tokens for the user.
    Errors are logged but not raised - tokens will expire naturally if revocation fails.
    """
    try:
        r = redis or await get_redis()
        keys_to_delete: list[str] = []

        # Revoke refresh tokens
        refresh_pattern = f"user_tokens:{user_id}:*"
        async for key in r.scan_iter(refresh_pattern):
            keys_to_delete.append(key)
            jti = key.split(":")[-1]
            keys_to_delete.append(f"refresh_token:{jti}")

        # Also revoke access tokens
        access_pattern = f"user_access_tokens:{user_id}:*"
        async for key in r.scan_iter(access_pattern):
            keys_to_delete.append(key)
            jti = key.split(":")[-1]
            keys_to_delete.append(f"access_token:{jti}")

        if keys_to_delete:
            await safe_redis_delete(*keys_to_delete, client=r)
    except RedisError as e:
        logger.warning(f"Failed to revoke all tokens for user {user_id}: {e}")
