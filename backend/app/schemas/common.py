from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int


class PaginationParams(BaseModel):
    """Pagination query parameters."""

    page: int = 1
    per_page: int = 20


class TimestampSchema(BaseModel):
    """Base schema with timestamp fields."""

    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    updated_at: datetime
