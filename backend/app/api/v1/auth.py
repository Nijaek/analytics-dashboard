from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.limiter import limiter
from app.core.redis import get_redis_dep
from app.core.security import (
    check_account_locked,
    clear_failed_logins,
    create_access_token,
    create_refresh_token,
    create_ws_ticket,
    decode_token,
    is_token_revoked,
    record_failed_login,
    revoke_all_user_access_tokens,
    revoke_token,
    store_access_token,
    store_refresh_token,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, Token
from app.schemas.user import UserResponse
from app.services.user_service import UserService

router = APIRouter()


class LogoutRequest(BaseModel):
    """Logout request body."""

    refresh_token: str


class LogoutResponse(BaseModel):
    """Logout response."""

    message: str = "Successfully logged out"


def _get_access_token_ttl_seconds() -> int:
    """Get access token TTL in seconds."""
    return settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def _get_refresh_token_ttl_seconds() -> int:
    """Get refresh token TTL in seconds."""
    return settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set HTTP-only auth cookies on the response."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=_get_access_token_ttl_seconds(),
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path=settings.COOKIE_PATH,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=_get_refresh_token_ttl_seconds(),
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/api/v1/auth",
    )
    # Non-HTTP-only cookie for client-side auth state detection
    response.set_cookie(
        key="logged_in",
        value="true",
        max_age=_get_refresh_token_ttl_seconds(),
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path=settings.COOKIE_PATH,
    )


def _clear_auth_cookies(response: Response) -> None:
    """Delete all auth cookies from the response."""
    for key, path in [
        ("access_token", settings.COOKIE_PATH),
        ("refresh_token", "/api/v1/auth"),
        ("logged_in", settings.COOKIE_PATH),
    ]:
        response.delete_cookie(
            key=key,
            domain=settings.COOKIE_DOMAIN,
            path=path,
        )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user."""
    service = UserService(db)

    existing = await service.get_by_email(data.email)
    if existing:
        raise ConflictError("Email already registered")

    user = await service.create(data)
    return user


async def _perform_login(user: User, redis: Redis) -> Token:
    """Create and store access + refresh tokens for an authenticated user."""
    if not user.is_active:
        raise UnauthorizedError("User is inactive")

    access_token, access_jti = create_access_token(user.id)
    refresh_token, refresh_jti = create_refresh_token(user.id)

    await store_access_token(
        user_id=user.id,
        jti=access_jti,
        expires_in_seconds=_get_access_token_ttl_seconds(),
        redis=redis,
    )
    await store_refresh_token(
        user_id=user.id,
        jti=refresh_jti,
        expires_in_seconds=_get_refresh_token_ttl_seconds(),
        redis=redis,
    )

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_dep),
):
    """Login and get access + refresh tokens (also set as HTTP-only cookies)."""
    if await check_account_locked(data.email, redis=redis):
        raise UnauthorizedError("Account temporarily locked. Try again in 15 minutes.")

    service = UserService(db)
    user = await service.authenticate(data.email, data.password)
    if not user:
        await record_failed_login(data.email, redis=redis)
        raise UnauthorizedError("Invalid email or password")

    await clear_failed_logins(data.email, redis=redis)
    token = await _perform_login(user, redis)
    response = JSONResponse(content=token.model_dump())
    _set_auth_cookies(response, token.access_token, token.refresh_token)
    return response


@router.post("/login/form", response_model=Token)
@limiter.limit("10/minute")
async def login_form(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_dep),
):
    """Login via form (for Swagger UI OAuth2 flow)."""
    if await check_account_locked(form_data.username, redis=redis):
        raise UnauthorizedError("Account temporarily locked. Try again in 15 minutes.")

    service = UserService(db)
    user = await service.authenticate(form_data.username, form_data.password)
    if not user:
        await record_failed_login(form_data.username, redis=redis)
        raise UnauthorizedError("Invalid email or password")

    await clear_failed_logins(form_data.username, redis=redis)
    token = await _perform_login(user, redis)
    response = JSONResponse(content=token.model_dump())
    _set_auth_cookies(response, token.access_token, token.refresh_token)
    return response


@router.post("/refresh", response_model=Token)
@limiter.limit("30/minute")
async def refresh_token_endpoint(
    request: Request,
    data: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_dep),
):
    """Refresh tokens — reads refresh token from cookie or request body."""
    # Cookie-first, body fallback
    raw_token = request.cookies.get("refresh_token")
    if not raw_token and data:
        raw_token = data.refresh_token
    if not raw_token:
        raise UnauthorizedError("No refresh token provided")

    payload = decode_token(raw_token)

    if not payload or payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid refresh token")

    user_id = payload.get("sub")
    jti = payload.get("jti")

    if not user_id or not jti:
        raise UnauthorizedError("Invalid token payload")

    # Check if token has been revoked
    if await is_token_revoked(jti, redis=redis):
        raise UnauthorizedError("Token has been revoked")

    service = UserService(db)
    user = await service.get(int(user_id))

    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    # Revoke old refresh token
    await revoke_token(jti, redis=redis)

    # Revoke all old access tokens for this user
    await revoke_all_user_access_tokens(user.id, redis=redis)

    # Create new tokens
    token = await _perform_login(user, redis)
    response = JSONResponse(content=token.model_dump())
    _set_auth_cookies(response, token.access_token, token.refresh_token)
    return response


@router.post("/logout", response_model=LogoutResponse)
@limiter.limit("30/minute")
async def logout(
    request: Request,
    data: LogoutRequest | None = None,
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis_dep),
):
    """Logout — revoke all tokens and clear auth cookies."""
    # Cookie-first, body fallback
    raw_token = request.cookies.get("refresh_token")
    if not raw_token and data:
        raw_token = data.refresh_token
    if not raw_token:
        raise UnauthorizedError("No refresh token provided")

    payload = decode_token(raw_token)

    if not payload or payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid refresh token")

    jti = payload.get("jti")
    user_id = payload.get("sub")
    if not jti or not user_id:
        raise UnauthorizedError("Invalid token payload")

    # Verify the refresh token belongs to the authenticated user
    if int(user_id) != current_user.id:
        raise UnauthorizedError("Token does not belong to current user")

    # Revoke the refresh token
    await revoke_token(jti, redis=redis)

    # Revoke all access tokens for this user
    await revoke_all_user_access_tokens(current_user.id, redis=redis)

    response = JSONResponse(content=LogoutResponse().model_dump())
    _clear_auth_cookies(response)
    return response


class WsTicketResponse(BaseModel):
    """WebSocket ticket response."""

    ticket: str


@router.post("/ws-ticket", response_model=WsTicketResponse)
async def get_ws_ticket(
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis_dep),
):
    """Get a short-lived single-use ticket for WebSocket authentication.

    Requires cookie or bearer auth. The ticket is valid for 30 seconds and single-use.
    """
    ticket = await create_ws_ticket(current_user.id, redis=redis)
    return WsTicketResponse(ticket=ticket)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info."""
    return current_user
