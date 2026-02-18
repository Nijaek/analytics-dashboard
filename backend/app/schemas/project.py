from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    name: str = Field(..., min_length=1, max_length=255)
    domain: str | None = Field(None, max_length=255)


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""

    name: str | None = Field(None, min_length=1, max_length=255)
    domain: str | None = None


class ProjectResponse(BaseModel):
    """Standard project response — shows key prefix only."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    api_key_prefix: str
    domain: str | None
    user_id: int
    created_at: datetime
    updated_at: datetime


class ProjectCreateResponse(ProjectResponse):
    """Response for create/rotate — includes full plaintext key (shown once)."""

    api_key: str
