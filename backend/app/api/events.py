"""Event ingestion and query endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
async def list_events(session: AsyncSession = Depends(get_session)):
    """List recent events (paginated)."""
    return {"events": [], "total": 0}
