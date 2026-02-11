from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter()


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def create_project(
    request: Request,
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new project. Returns the project with its API key."""
    service = ProjectService(db)
    return await service.create(user_id=current_user.id, data=data)


@router.get("/", response_model=list[ProjectResponse])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def list_projects(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all projects for the current user."""
    service = ProjectService(db)
    return await service.list_by_user(user_id=current_user.id)


@router.get("/{project_id}", response_model=ProjectResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def get_project(
    request: Request,
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific project by ID."""
    service = ProjectService(db)
    return await service.get(project_id=project_id, user_id=current_user.id)


@router.patch("/{project_id}", response_model=ProjectResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def update_project(
    request: Request,
    project_id: int,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a project."""
    service = ProjectService(db)
    return await service.update(project_id=project_id, user_id=current_user.id, data=data)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def delete_project(
    request: Request,
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a project."""
    service = ProjectService(db)
    await service.delete(project_id=project_id, user_id=current_user.id)
    return None


@router.post("/{project_id}/rotate-key", response_model=ProjectResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def rotate_api_key(
    request: Request,
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rotate the API key for a project."""
    service = ProjectService(db)
    return await service.rotate_api_key(project_id=project_id, user_id=current_user.id)
