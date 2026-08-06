"""Pydantic schemas for the user model."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field


def _coerce_uuid(v):
    """Convert UUID objects to strings before str validation."""
    return str(v) if isinstance(v, UUID) else v


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=6, max_length=255)
    role: str = "analyst"


class UserLogin(BaseModel):
    """Schema for login (username and password)."""

    username: str
    password: str


class UserRead(BaseModel):
    """User read schema (never exposes the password)."""

    id: Annotated[str, BeforeValidator(_coerce_uuid)]
    username: str
    role: str
    active: bool

    model_config = {"from_attributes": True}
