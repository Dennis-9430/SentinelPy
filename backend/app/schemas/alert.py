"""Pydantic schemas for Alert."""

from datetime import datetime
from pydantic import BaseModel


class AlertRead(BaseModel):
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
