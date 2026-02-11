from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token, is_access_token_revoked
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.services.project_service import ProjectService
from app.services.user_service import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login/form")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency to get the current authenticated user from JWT token."""
    payload = decode_token(token)

    if not payload:
        raise UnauthorizedError("Invalid token")

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")

    user_id = payload.get("sub")
    jti = payload.get("jti")
    if not user_id or not jti:
        raise UnauthorizedError("Invalid token payload")

    # Check if access token has been revoked
    if await is_access_token_revoked(jti):
        raise UnauthorizedError("Token has been revoked")

    service = UserService(db)
    user = await service.get(int(user_id))

    if not user:
        raise UnauthorizedError("User not found")

    if not user.is_active:
        raise UnauthorizedError("User is inactive")

    return user


async def get_current_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency to ensure the current user is a superuser."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


async def get_project_by_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Dependency to authenticate requests via project API key."""
    service = ProjectService(db)
    project = await service.get_by_api_key(x_api_key)
    if not project:
        raise UnauthorizedError("Invalid API key")
    return project
