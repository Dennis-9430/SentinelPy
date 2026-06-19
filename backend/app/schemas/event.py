"""Esquemas Pydantic para el modelo NormalizedEvent.

Pydantic valida los datos de entrada (request) y define
la estructura de salida (response) de la API.
"""

from datetime import datetime
from pydantic import BaseModel


class EventCreate(BaseModel):
    """Esquema de entrada para crear un evento.

    Se usa en POST /api/events/ para recibir datos del colector.
    Todos los campos opcionales son None por defecto.
    """

    source: str
    collector_type: str
    event_timestamp: datetime
    event_type: str
    severity: str
    description: str
    source_ip: str | None = None
    destination_ip: str | None = None
    source_port: int | None = None
    destination_port: int | None = None
    protocol: str | None = None
    user_name: str | None = None
    process_name: str | None = None
    file_path: str | None = None
    raw_log: str | None = None


class EventRead(EventCreate):
    """Esquema de salida — incluye campos de base de datos.

    from_attributes permite crear instancias desde objetos SQLAlchemy.
    """

    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
