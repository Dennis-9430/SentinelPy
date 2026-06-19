"""Detection rule CRUD endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("")
async def list_rules(session: AsyncSession = Depends(get_session)):
    """List all detection rules."""
    return {"rules": [], "total": 0}
