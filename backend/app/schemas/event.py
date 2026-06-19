"""Pydantic schemas for NormalizedEvent."""

from datetime import datetime
from pydantic import BaseModel


class EventCreate(BaseModel):
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
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
