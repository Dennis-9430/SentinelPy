"""Pydantic schemas para Threat Intelligence endpoints.

Define request/response models para los endpoints de:
- Lookup manual de IOCs
- Listado de feeds/providers
- Listado de IOCs cacheados
"""

from pydantic import BaseModel, Field


class LookupRequest(BaseModel):
    """Request schema for manual IOC lookup."""

    indicator: str = Field(
        ..., min_length=1, max_length=500, description="IOC indicator value"
    )
    ioc_type: str = Field(
        ...,
        pattern=r"^(ip|domain|hash|url)$",
        description="IOC type",
    )


class IOCResultResponse(BaseModel):
    """Response schema for IOC lookup result."""

    indicator: str
    ioc_type: str
    confidence: int = Field(ge=0, le=100)
    provider: str


class FeedResponse(BaseModel):
    """Response schema for a single TI feed."""

    name: str
    status: str
    supported_types: list[str]


class FeedListResponse(BaseModel):
    """Response schema for list of TI feeds."""

    feeds: list[FeedResponse]


class IOCEntryResponse(BaseModel):
    """Response schema for a cached IOC entry."""

    id: str
    indicator: str
    ioc_type: str
    provider: str
    confidence: int
    first_seen: str | None = None
    last_seen: str | None = None
    expires_at: str | None = None


class IOCListResponse(BaseModel):
    """Response schema for paginated IOC list."""

    iocs: list[IOCEntryResponse]
    total: int
