"""Esquemas Pydantic para el modelo Alert."""

from datetime import datetime
from pydantic import BaseModel


class AlertRead(BaseModel):
    """Esquema de salida para alertas.

    Solo lectura — las alertas se crean internamente por el motor de correlación,
    no por la API directamente.
    """

    id: str
    rule_id: str
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


class AlertUpdateStatus(BaseModel):
    """Esquema para actualizar el estado de una alerta."""

    status: str
    resolution_notes: str | None = None
