from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.limiter import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    is_token_revoked,
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


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
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


@router.post("/login", response_model=Token)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Login and get access + refresh tokens."""
    service = UserService(db)

    user = await service.authenticate(data.email, data.password)
    if not user:
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        raise UnauthorizedError("User is inactive")

    access_token, access_jti = create_access_token(user.id)
    refresh_token, refresh_jti = create_refresh_token(user.id)

    # Store access token in Redis
    await store_access_token(
        user_id=user.id,
        jti=access_jti,
        expires_in_seconds=_get_access_token_ttl_seconds(),
    )

    # Store refresh token in Redis
    await store_refresh_token(
        user_id=user.id,
        jti=refresh_jti,
        expires_in_seconds=_get_refresh_token_ttl_seconds(),
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/login/form", response_model=Token)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def login_form(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login via form (for Swagger UI OAuth2 flow)."""
    service = UserService(db)

    user = await service.authenticate(form_data.username, form_data.password)
    if not user:
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        raise UnauthorizedError("User is inactive")

    access_token, access_jti = create_access_token(user.id)
    refresh_token, refresh_jti = create_refresh_token(user.id)

    # Store access token in Redis
    await store_access_token(
        user_id=user.id,
        jti=access_jti,
        expires_in_seconds=_get_access_token_ttl_seconds(),
    )

    # Store refresh token in Redis
    await store_refresh_token(
        user_id=user.id,
        jti=refresh_jti,
        expires_in_seconds=_get_refresh_token_ttl_seconds(),
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=Token)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def refresh_token_endpoint(
    request: Request,
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Get new access token using refresh token."""
    payload = decode_token(data.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid refresh token")

    user_id = payload.get("sub")
    jti = payload.get("jti")

    if not user_id or not jti:
        raise UnauthorizedError("Invalid token payload")

    # Check if token has been revoked
    if await is_token_revoked(jti):
        raise UnauthorizedError("Token has been revoked")

    service = UserService(db)
    user = await service.get(int(user_id))

    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    # Revoke old refresh token
    await revoke_token(jti)

    # Revoke all old access tokens for this user
    await revoke_all_user_access_tokens(user.id)

    # Create new tokens
    access_token, access_jti = create_access_token(user.id)
    new_refresh_token, new_refresh_jti = create_refresh_token(user.id)

    # Store new access token
    await store_access_token(
        user_id=user.id,
        jti=access_jti,
        expires_in_seconds=_get_access_token_ttl_seconds(),
    )

    # Store new refresh token
    await store_refresh_token(
        user_id=user.id,
        jti=new_refresh_jti,
        expires_in_seconds=_get_refresh_token_ttl_seconds(),
    )

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.post("/logout", response_model=LogoutResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def logout(
    request: Request,
    data: LogoutRequest,
):
    """Logout and revoke all tokens for the user."""
    payload = decode_token(data.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid refresh token")

    jti = payload.get("jti")
    user_id = payload.get("sub")
    if not jti or not user_id:
        raise UnauthorizedError("Invalid token payload")

    # Revoke the refresh token
    await revoke_token(jti)

    # Revoke all access tokens for this user
    await revoke_all_user_access_tokens(int(user_id))

    return LogoutResponse()


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info."""
    return current_user
