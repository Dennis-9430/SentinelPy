"""Esquemas Pydantic para el modelo Alert."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator


def _coerce_uuid(v):
    """Convert UUID objects to strings before str validation."""
    return str(v) if isinstance(v, UUID) else v


class AlertRead(BaseModel):
    """Esquema de salida para alertas.

    Solo lectura — las alertas se crean internamente por el motor de correlación,
    no por la API directamente.
    """

    id: Annotated[str, BeforeValidator(_coerce_uuid)]
    rule_id: Annotated[str, BeforeValidator(_coerce_uuid)]
    title: str
    severity: str
    description: str
    status: str
    event_count: int
    first_event_at: datetime | None = None
    last_event_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    resolution_notes: str | None = None

    model_config = {"from_attributes": True}


class AlertListItem(BaseModel):
    """Esquema ligero para listado de alertas (sin description completa)."""

    id: Annotated[str, BeforeValidator(_coerce_uuid)]
    rule_id: Annotated[str, BeforeValidator(_coerce_uuid)]
    title: str
    severity: str
    description: str = ""
    status: str
    event_count: int
    first_event_at: datetime | None = None
    last_event_at: datetime | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class AlertListResponse(BaseModel):
    """Respuesta paginada de alertas."""

    alertas: list[AlertListItem]
    total: int


class AlertUpdateStatus(BaseModel):
    """Esquema para actualizar el estado de una alerta."""

    status: str
    resolution_notes: str | None = None


class AlertUpdateResponse(BaseModel):
    """Respuesta al actualizar estado de alerta."""

    id: Annotated[str, BeforeValidator(_coerce_uuid)]
    status: str
    resolved_at: datetime | None = None
    updated_at: datetime


class AlertGroupAlert(BaseModel):
    """Alerta dentro de un grupo."""

    id: Annotated[str, BeforeValidator(_coerce_uuid)]
    rule_id: Annotated[str, BeforeValidator(_coerce_uuid)]
    title: str
    severity: str
    description: str = ""
    status: str
    group_key: str | None = None
    group_name: str | None = None
    risk_score: float | None = None
    event_count: int
    created_at: datetime


class AlertGroup(BaseModel):
    """Grupo de alertas agrupadas por group_key."""

    group_key: str
    group_name: str
    alert_count: int
    max_severity: str
    risk_score: float | None = None
    alerts: list[AlertGroupAlert]


class AlertGroupListResponse(BaseModel):
    """Respuesta de listado de grupos de alertas."""

    groups: list[AlertGroup]
    total: int


class AlertStatsResponse(BaseModel):
    """Estadísticas de alertas."""

    por_severidad: dict[str, int]
    por_estado: dict[str, int]
