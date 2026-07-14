"""Esquemas de respuesta estándar para la API.

Wrapper genérico para respuestas paginadas y schema de error
que todos los endpoints deben usar.
"""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Schema de error estándar para la API."""

    detail: str
    code: str | None = None


class PaginationMeta(BaseModel):
    """Metadata de paginación."""

    total: int
    page: int = 1
    per_page: int = 50


class PaginatedResponse(BaseModel, extra="forbid"):
    """Respuesta paginada genérica."""

    items: list
    meta: PaginationMeta


class HealthResponse(BaseModel):
    """Respuesta del health check."""

    status: str
    app: str
    version: str
    reglas_activas: int = 0
    ventanas_activas: int = 0


class EventTimeline(BaseModel):
    """Punto en la línea de tiempo de eventos."""

    hora: str
    total: int


class EventStatsResponse(BaseModel):
    """Estadísticas de eventos para el dashboard."""

    timeline: list[EventTimeline]
    por_severidad: dict[str, int]


class AlertStatsResponse(BaseModel):
    """Estadísticas de alertas para el dashboard."""

    por_severidad: dict[str, int]
    por_estado: dict[str, int]
