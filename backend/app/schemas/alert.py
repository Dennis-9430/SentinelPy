"""Pydantic schemas for the Alert model."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator


def _coerce_uuid(v):
    """Convert UUID objects to strings before str validation."""
    return str(v) if isinstance(v, UUID) else v


class AlertRead(BaseModel):
    """Output schema for alerts.

    Read-only — alerts are created internally by the correlation engine,
    not directly by the API.
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
    """Light schema for alert listing (without the full description)."""

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
    """Paginated alerts response."""

    alertas: list[AlertListItem]
    total: int


class AlertUpdateStatus(BaseModel):
    """Schema for updating an alert's status."""

    status: str
    resolution_notes: str | None = None


class AlertUpdateResponse(BaseModel):
    """Response to an alert status update."""

    id: Annotated[str, BeforeValidator(_coerce_uuid)]
    status: str
    resolved_at: datetime | None = None
    updated_at: datetime


class AlertGroupAlert(BaseModel):
    """Alert within a group."""

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
    """Group of alerts grouped by group_key."""

    group_key: str
    group_name: str
    alert_count: int
    max_severity: str
    risk_score: float | None = None
    alerts: list[AlertGroupAlert]


class AlertGroupListResponse(BaseModel):
    """Alert groups listing response."""

    groups: list[AlertGroup]
    total: int


class AlertStatsResponse(BaseModel):
    """Alert statistics."""

    por_severidad: dict[str, int]
    por_estado: dict[str, int]
