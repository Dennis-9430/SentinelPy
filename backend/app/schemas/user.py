"""Esquemas Pydantic para el modelo de usuario."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field


def _coerce_uuid(v):
    """Convert UUID objects to strings before str validation."""
    return str(v) if isinstance(v, UUID) else v


class UserCreate(BaseModel):
    """Esquema para crear un nuevo usuario."""

    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=6, max_length=255)
    role: str = "analyst"


class UserLogin(BaseModel):
    """Esquema para login (usuario y contraseña)."""

    username: str
    password: str


class UserRead(BaseModel):
    """Esquema de lectura de usuario (nunca expone el password)."""

    id: Annotated[str, BeforeValidator(_coerce_uuid)]
    username: str
    role: str
    active: bool

    model_config = {"from_attributes": True}
