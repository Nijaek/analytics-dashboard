import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
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


async def store_access_token(user_id: int, jti: str, expires_in_seconds: int) -> None:
    """Store access token JTI in Redis.

    Stores both the token lookup key and a user->token mapping for bulk revocation.

    Raises:
        ServiceUnavailableError: If Redis is unavailable.
    """
    # Store the access token with TTL
    token_key = f"access_token:{jti}"
    await safe_redis_setex(token_key, expires_in_seconds, str(user_id), raise_on_error=True)
    # Store user->token mapping for bulk revocation
    user_token_key = f"user_access_tokens:{user_id}:{jti}"
    await safe_redis_setex(user_token_key, expires_in_seconds, "1", raise_on_error=True)


async def is_access_token_revoked(jti: str) -> bool:
    """Check if an access token has been revoked.

    A token is considered revoked if it doesn't exist in Redis.
    Uses fail-closed behavior: if Redis is unavailable, treats token as revoked.
    """
    key = f"access_token:{jti}"
    # fail_closed=True means if Redis fails, key "doesn't exist" = token is revoked
    return not await safe_redis_exists(key, fail_closed=True)


async def revoke_access_token(jti: str) -> None:
    """Revoke a single access token.

    Errors are logged but not raised - token will expire naturally if revocation fails.
    """
    try:
        redis = await get_redis()
        # Get user_id from token before deleting
        token_key = f"access_token:{jti}"
        user_id = await redis.get(token_key)
        await safe_redis_delete(token_key)
        # Also delete user->token mapping if we found the user
        if user_id:
            user_token_key = f"user_access_tokens:{user_id}:{jti}"
            await safe_redis_delete(user_token_key)
    except RedisError as e:
        logger.warning(f"Failed to revoke access token {jti}: {e}")


async def revoke_all_user_access_tokens(user_id: int) -> None:
    """Revoke all access tokens for a user (e.g., on logout or password change).

    Uses pattern matching to find and delete all access tokens for the user.
    Errors are logged but not raised - tokens will expire naturally if revocation fails.
    """
    try:
        redis = await get_redis()
        pattern = f"user_access_tokens:{user_id}:*"
        # Collect all JTIs first, then delete
        keys_to_delete: list[str] = []
        async for key in redis.scan_iter(pattern):
            keys_to_delete.append(key)
            # Extract JTI from key and add access_token key
            jti = key.split(":")[-1]
            keys_to_delete.append(f"access_token:{jti}")
        # Delete all keys
        if keys_to_delete:
            await safe_redis_delete(*keys_to_delete)
    except RedisError as e:
        logger.warning(f"Failed to revoke all access tokens for user {user_id}: {e}")


async def store_refresh_token(user_id: int, jti: str, expires_in_seconds: int) -> None:
    """Store refresh token JTI in Redis.

    Stores both the token lookup key and a user->token mapping for bulk revocation.

    Raises:
        ServiceUnavailableError: If Redis is unavailable.
    """
    # Store the refresh token with TTL
    token_key = f"refresh_token:{jti}"
    await safe_redis_setex(token_key, expires_in_seconds, str(user_id), raise_on_error=True)
    # Store user->token mapping for bulk revocation
    user_token_key = f"user_tokens:{user_id}:{jti}"
    await safe_redis_setex(user_token_key, expires_in_seconds, "1", raise_on_error=True)


async def is_token_revoked(jti: str) -> bool:
    """Check if a refresh token has been revoked.

    A token is considered revoked if it doesn't exist in Redis.
    Uses fail-closed behavior: if Redis is unavailable, treats token as revoked.
    """
    key = f"refresh_token:{jti}"
    # fail_closed=True means if Redis fails, key "doesn't exist" = token is revoked
    return not await safe_redis_exists(key, fail_closed=True)


async def revoke_token(jti: str) -> None:
    """Revoke a single refresh token.

    Errors are logged but not raised - token will expire naturally if revocation fails.
    """
    try:
        redis = await get_redis()
        # Get user_id from token before deleting
        token_key = f"refresh_token:{jti}"
        user_id = await redis.get(token_key)
        await safe_redis_delete(token_key)
        # Also delete user->token mapping if we found the user
        if user_id:
            user_token_key = f"user_tokens:{user_id}:{jti}"
            await safe_redis_delete(user_token_key)
    except RedisError as e:
        logger.warning(f"Failed to revoke token {jti}: {e}")


# --- Account lockout ---

LOCKOUT_PREFIX = "login_failures:"
MAX_LOGIN_FAILURES = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minutes


async def check_account_locked(email: str) -> bool:
    """Check if an account is locked due to too many failed login attempts."""
    key = f"{LOCKOUT_PREFIX}{email}"
    try:
        r = await get_redis()
        failures = await r.get(key)
        return failures is not None and int(failures) >= MAX_LOGIN_FAILURES
    except (RedisError, Exception):
        return False  # Fail-open: don't lock out if Redis is down


async def record_failed_login(email: str) -> None:
    """Increment failed login counter with TTL."""
    key = f"{LOCKOUT_PREFIX}{email}"
    try:
        r = await get_redis()
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, LOCKOUT_SECONDS)
        await pipe.execute()
    except (RedisError, Exception) as exc:
        logger.warning("Failed to record login failure for %s: %s", email, exc)


async def clear_failed_logins(email: str) -> None:
    """Reset failed login counter on successful login."""
    key = f"{LOCKOUT_PREFIX}{email}"
    await safe_redis_delete(key)


async def revoke_all_user_tokens(user_id: int) -> None:
    """Revoke all tokens (access and refresh) for a user (e.g., on password change).

    Uses pattern matching to find and delete all tokens for the user.
    Errors are logged but not raised - tokens will expire naturally if revocation fails.
    """
    try:
        redis = await get_redis()
        keys_to_delete: list[str] = []

        # Revoke refresh tokens
        refresh_pattern = f"user_tokens:{user_id}:*"
        async for key in redis.scan_iter(refresh_pattern):
            keys_to_delete.append(key)
            jti = key.split(":")[-1]
            keys_to_delete.append(f"refresh_token:{jti}")

        # Also revoke access tokens
        access_pattern = f"user_access_tokens:{user_id}:*"
        async for key in redis.scan_iter(access_pattern):
            keys_to_delete.append(key)
            jti = key.split(":")[-1]
            keys_to_delete.append(f"access_token:{jti}")

        # Delete all keys
        if keys_to_delete:
            await safe_redis_delete(*keys_to_delete)
    except RedisError as e:
        logger.warning(f"Failed to revoke all tokens for user {user_id}: {e}")
