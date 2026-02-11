from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_superuser, get_current_user
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.user import PasswordChange, PasswordReset, UserResponse, UserUpdate
from app.services.user_service import UserService

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[UserResponse])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def list_users(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """List all users (superuser only)."""
    service = UserService(db)
    skip = (page - 1) * per_page

    users, total = await service.get_multi(skip=skip, limit=per_page)
    pages = (total + per_page - 1) // per_page

    return PaginatedResponse(
        items=users,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get("/{user_id}", response_model=UserResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def get_user(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific user by ID."""
    # Users can only view their own profile unless superuser
    if current_user.id != user_id and not current_user.is_superuser:
        raise NotFoundError("User not found")

    service = UserService(db)
    user = await service.get(user_id)

    if not user:
        raise NotFoundError("User not found")

    return user


@router.patch("/{user_id}", response_model=UserResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def update_user(
    request: Request,
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a user (own profile or superuser)."""
    if current_user.id != user_id and not current_user.is_superuser:
        raise NotFoundError("User not found")

    service = UserService(db)
    user = await service.get(user_id)

    if not user:
        raise NotFoundError("User not found")

    # Handle email update with race condition protection
    if data.email and data.email != user.email:
        await service.update_email(user, data.email)

    # Update other fields (email handled above)
    update_data = data.model_dump(exclude_unset=True, exclude={"email"})
    for field, value in update_data.items():
        setattr(user, field, value)
    await service.db.flush()
    await service.db.refresh(user)
    return user


@router.post("/me/password", status_code=204)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def change_password(
    request: Request,
    data: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change the current user's password (requires current password verification)."""
    service = UserService(db)
    await service.update_password(
        user=current_user,
        new_password=data.new_password,
        current_password=data.current_password,
    )
    return None


@router.post("/{user_id}/password", status_code=204)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def reset_user_password(
    request: Request,
    user_id: int,
    data: PasswordReset,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Reset a user's password (superuser only, no current password required)."""
    service = UserService(db)
    user = await service.get(user_id)

    if not user:
        raise NotFoundError("User not found")

    await service.update_password(
        user=user,
        new_password=data.new_password,
        skip_verification=True,
    )
    return None


@router.delete("/{user_id}", status_code=204)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def delete_user(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Delete a user (superuser only)."""
    service = UserService(db)

    if not await service.delete(user_id):
        raise NotFoundError("User not found")

    return None
