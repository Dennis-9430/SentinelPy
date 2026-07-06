"""Esquemas Pydantic para el modelo Agent.

Separa los esquemas de creación (incluye api_key_raw una sola vez)
de los de lectura (nunca expone api_key_hash) y listado.
"""

from datetime import datetime
from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    """Esquema para crear un nuevo agente remoto.

    Solo requiere name y hostname. El servidor genera la API key
    automáticamente con secrets.token_urlsafe(32).
    """

    name: str = Field(min_length=1, max_length=100, description="Nombre único del agente")
    hostname: str = Field(min_length=1, max_length=255, description="Hostname del equipo")


class AgentRead(BaseModel):
    """Esquema de lectura de agente (nunca expone api_key_hash).

    La API key raw SOLO se retorna en la respuesta de creación
    (ver AgentCreateResponse). Ningún GET/PATCH/PUT incluye
    api_key_hash ni api_key_raw.
    """

    id: int
    name: str
    hostname: str
    last_seen: datetime | None = None
    active: bool
    version: str | None = None
    heartbeat_timeout_minutes: int = 5
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentUpdate(BaseModel):
    """Esquema para actualizar campos de un agente.

    Todos los campos son opcionales — solo se actualizan
    los que se envían. Se requiere al menos uno.
    """

    name: str | None = Field(
        default=None, min_length=1, max_length=100,
        description="Nuevo nombre del agente",
    )
    hostname: str | None = Field(
        default=None, min_length=1, max_length=255,
        description="Nuevo hostname del agente",
    )


class AgentCreateResponse(AgentRead):
    """Respuesta de creación — incluye api_key_raw UNA SOLA VEZ.

    Este esquema SOLO se usa en la respuesta 201 de POST /api/admin/agents.
    api_key_raw nunca se almacena ni se puede recuperar después.
    """

    api_key_raw: str


class AgentList(BaseModel):
    """Esquema de listado de agentes con total."""

    agents: list[AgentRead]
    total: int
