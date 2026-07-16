"""Endpoints de la API para Threat Intelligence.

Listado de feeds/providers, lookup manual de IOCs,
y listado de IOCs cacheados en base de datos.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.threat_intel import (
    FeedListResponse,
    FeedResponse,
    IOCEntryResponse,
    IOCListResponse,
    IOCResultResponse,
    LookupRequest,
)

router = APIRouter(prefix="/threat-intel", tags=["Threat Intelligence"])


@router.get("/feeds", response_model=FeedListResponse)
async def list_feeds():
    """List status of all registered TI providers."""
    from app.main import app

    ti_service = getattr(app.state, "ti_service", None)
    if not ti_service:
        return FeedListResponse(feeds=[])

    feeds = [
        FeedResponse(
            name=f["name"],
            status=f["status"],
            supported_types=f["supported_types"],
        )
        for f in ti_service.feeds
    ]
    return FeedListResponse(feeds=feeds)


@router.post("/lookup", response_model=IOCResultResponse)
async def lookup_ioc(request: LookupRequest):
    """Manual IOC lookup across all providers."""
    from app.main import app

    ti_service = getattr(app.state, "ti_service", None)
    if not ti_service:
        raise HTTPException(
            status_code=503,
            detail="Threat Intelligence service not available",
        )

    result = await ti_service.lookup(request.indicator, request.ioc_type)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="No results found for this indicator",
        )

    return IOCResultResponse(
        indicator=result.indicator,
        ioc_type=result.ioc_type,
        confidence=result.confidence,
        provider=result.provider,
    )


@router.get("/iocs", response_model=IOCListResponse)
async def list_iocs(
    limit: int = Query(50, ge=1, le=500, description="Max IOCs per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: AsyncSession = Depends(get_session),
):
    """List cached IOC entries (paginated)."""
    from app.models.threat_intel import IOCEntry

    # Count total
    count_stmt = select(func.count()).select_from(IOCEntry)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Fetch page
    stmt = (
        select(IOCEntry)
        .order_by(IOCEntry.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    iocs = result.scalars().all()

    return IOCListResponse(
        iocs=[
            IOCEntryResponse(
                id=str(ioc.id),
                indicator=ioc.indicator,
                ioc_type=ioc.ioc_type,
                provider=ioc.provider,
                confidence=ioc.confidence,
                first_seen=ioc.first_seen.isoformat() if ioc.first_seen else None,
                last_seen=ioc.last_seen.isoformat() if ioc.last_seen else None,
                expires_at=ioc.expires_at.isoformat() if ioc.expires_at else None,
            )
            for ioc in iocs
        ],
        total=total,
    )
