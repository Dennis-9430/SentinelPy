"""Pydantic schemas for the Agent model.

Separates the creation schemas (include api_key_raw once)
from the read (never expose api_key_hash) and listing ones.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    """Schema for creating a new remote agent.

    Only requires name and hostname. The server generates the API key
    automatically with secrets.token_urlsafe(32).
    """

    name: str = Field(
        min_length=1, max_length=100, description="Unique agent name"
    )
    hostname: str = Field(
        min_length=1, max_length=255, description="Machine hostname"
    )



class AgentRead(BaseModel):
    """Agent read schema (never exposes api_key_hash).

    The raw API key is ONLY returned in the creation response
    (see AgentCreateResponse). No GET/PATCH/PUT includes
    api_key_hash or api_key_raw.
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
    """Schema for updating an agent's fields.

    All fields are optional — only the ones sent are updated.
    At least one is required.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="New agent name",
    )
    hostname: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="New agent hostname",
    )


class AgentCreateResponse(AgentRead):
    """Creation response — includes api_key_raw ONLY ONCE.

    This schema is ONLY used in the 201 response of POST /api/admin/agents.
    api_key_raw is never stored and cannot be retrieved afterwards.
    """

    api_key_raw: str


class AgentList(BaseModel):
    """Paginated agent listing schema with total."""

    agents: list[AgentRead]
    total: int
    page: int = 1
    per_page: int = 10
