from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError
from app.core.security import hash_password, revoke_all_user_tokens, verify_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.base import BaseService


class UserService(BaseService[User, UserCreate, UserUpdate]):
    """Service for user-related operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def get_by_email(self, email: str) -> User | None:
        """Get a user by email address."""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, obj_in: UserCreate) -> User:
        """Create a new user with hashed password.

        Raises:
            ConflictError: If email already exists (handles race conditions).
        """
        db_obj = User(
            email=obj_in.email,
            hashed_password=hash_password(obj_in.password),
            full_name=obj_in.full_name,
        )
        self.db.add(db_obj)
        try:
            await self.db.flush()
        except IntegrityError as e:
            await self.db.rollback()
            if "unique" in str(e.orig).lower() or "duplicate" in str(e.orig).lower():
                raise ConflictError("Email already registered") from None
            raise
        await self.db.refresh(db_obj)
        return db_obj

    async def update_email(self, user: User, new_email: str) -> User:
        """Update user email with race condition handling.

        Raises:
            ConflictError: If email already in use.
        """
        old_email = user.email
        user.email = new_email
        try:
            await self.db.flush()
        except IntegrityError as e:
            await self.db.rollback()
            user.email = old_email
            if "unique" in str(e.orig).lower() or "duplicate" in str(e.orig).lower():
                raise ConflictError("Email already in use") from None
            raise
        await self.db.refresh(user)
        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        """Authenticate a user by email and password."""
        user = await self.get_by_email(email)
        if not user:
            # Run bcrypt anyway to prevent timing attacks
            verify_password(
                password, "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.S9h0vqXp1V.1Wy"
            )
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def update_password(
        self,
        user: User,
        new_password: str,
        current_password: str | None = None,
        skip_verification: bool = False,
    ) -> User:
        """Update a user's password and revoke all existing tokens.

        Args:
            user: The user to update.
            new_password: The new password.
            current_password: The current password (required unless skip_verification=True).
            skip_verification: If True, skip current password check (for superuser override).

        Raises:
            BadRequestError: If current password is incorrect.
        """
        if not skip_verification:
            if current_password is None:
                raise BadRequestError("Current password is required")
            if not verify_password(current_password, user.hashed_password):
                raise BadRequestError("Current password is incorrect")

        user.hashed_password = hash_password(new_password)
        await self.db.flush()
        await self.db.refresh(user)
        # Revoke all existing refresh tokens for security
        await revoke_all_user_tokens(user.id)
        return user
