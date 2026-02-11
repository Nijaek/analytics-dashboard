import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceUnavailableError
from app.db.session import get_db
from app.schemas.common import MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=MessageResponse)
async def health_check():
    """Basic health check endpoint."""
    return {"message": "healthy"}


@router.get("/ready", response_model=MessageResponse)
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness check - verifies database connection is working."""
    try:
        await db.execute(text("SELECT 1"))
        return {"message": "ready"}
    except Exception:
        logger.error("Readiness check failed: database connection error")
        raise ServiceUnavailableError(detail="Service not ready") from None
