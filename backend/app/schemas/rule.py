"""Esquemas Pydantic para el modelo DetectionRule."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator


def _coerce_uuid(v):
    """Convert UUID objects to strings before str validation."""
    return str(v) if isinstance(v, UUID) else v


class RuleCreate(BaseModel):
    """Esquema de entrada para crear o actualizar una regla.

    conditions es un dict JSON con la lógica de detección.
    Ejemplo: {"field": "event_type", "operator": "eq", "value": "auth_failure"}
    """

    title: str
    description: str
    author: str | None = None
    severity: str = "medium"
    status: str = "active"
    conditions: dict
    correlation_window: int | None = None
    alert_title: str
    alert_severity: str = "medium"
    tags: list = []
    references: list = []
    false_positives: str | None = None


class RuleRead(RuleCreate):
    """Esquema de salida con campos de base de datos."""

    id: Annotated[str, BeforeValidator(_coerce_uuid)]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
