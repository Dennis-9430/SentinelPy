"""Standard response schemas for the API.

Generic wrapper for paginated responses and the error schema
that all endpoints must use.
"""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error schema for the API."""

    detail: str
    code: str | None = None


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    total: int
    page: int = 1
    per_page: int = 50


class PaginatedResponse(BaseModel, extra="forbid"):
    """Generic paginated response."""

    items: list
    meta: PaginationMeta


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    app: str
    version: str
    reglas_activas: int = 0
    ventanas_activas: int = 0


class EventTimeline(BaseModel):
    """Point in the event timeline."""

    hora: str
    total: int


class EventStatsResponse(BaseModel):
    """Event statistics for the dashboard."""

    timeline: list[EventTimeline]
    por_severidad: dict[str, int]


class AlertStatsResponse(BaseModel):
    """Alert statistics for the dashboard."""

    por_severidad: dict[str, int]
    por_estado: dict[str, int]
