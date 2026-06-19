"""Pydantic schemas for DetectionRule."""

from datetime import datetime
from pydantic import BaseModel


class RuleCreate(BaseModel):
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
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
