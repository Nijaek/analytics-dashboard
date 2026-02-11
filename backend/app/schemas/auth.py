from pydantic import BaseModel, EmailStr

from app.schemas.user import UserCreate


class Token(BaseModel):
    """JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: int | None = None
    exp: int | None = None
    type: str | None = None


class LoginRequest(BaseModel):
    """Login request body."""

    email: EmailStr
    password: str


class RegisterRequest(UserCreate):
    """User registration request body (inherits from UserCreate)."""

    pass


class RefreshRequest(BaseModel):
    """Token refresh request body."""

    refresh_token: str
