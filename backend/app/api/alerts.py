"""Alert listing and management endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(session: AsyncSession = Depends(get_session)):
    """List alerts with optional status filter."""
    return {"alerts": [], "total": 0}
