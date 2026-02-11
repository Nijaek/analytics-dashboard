from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectService:
    """Service for project CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: int, data: ProjectCreate) -> Project:
        """Create a new project with auto-generated API key."""
        project = Project(
            user_id=user_id,
            name=data.name,
            domain=data.domain,
            api_key=Project.generate_api_key(),
        )
        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def get(self, project_id: int, user_id: int) -> Project:
        """Get a project by ID, ensuring it belongs to the user."""
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise NotFoundError("Project not found")
        if project.user_id != user_id:
            raise ForbiddenError("Not authorized to access this project")
        return project

    async def list_by_user(self, user_id: int) -> list[Project]:
        """List all projects for a user."""
        result = await self.db.execute(
            select(Project).where(Project.user_id == user_id).order_by(Project.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, project_id: int, user_id: int, data: ProjectUpdate) -> Project:
        """Update a project."""
        project = await self.get(project_id, user_id)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(project, field, value)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def delete(self, project_id: int, user_id: int) -> None:
        """Delete a project."""
        project = await self.get(project_id, user_id)
        await self.db.delete(project)
        await self.db.flush()

    async def rotate_api_key(self, project_id: int, user_id: int) -> Project:
        """Rotate the API key for a project."""
        project = await self.get(project_id, user_id)
        project.api_key = Project.generate_api_key()
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def get_by_api_key(self, api_key: str) -> Project | None:
        """Get a project by its API key (for event ingestion)."""
        result = await self.db.execute(select(Project).where(Project.api_key == api_key))
        return result.scalar_one_or_none()
