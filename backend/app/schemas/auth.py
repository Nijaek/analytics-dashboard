from pydantic import BaseModel, EmailStr

from app.schemas.user import UserCreate


class Token(BaseModel):
    """JWT token response (used for form-based login / Swagger UI only)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """Login response — tokens are delivered via HTTP-only cookies."""

    message: str = "Login successful"


class RefreshResponse(BaseModel):
    """Token refresh response — new tokens set via HTTP-only cookies."""

    message: str = "Token refreshed"


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
    """Token refresh request body (fallback when cookie is unavailable)."""

    refresh_token: str
