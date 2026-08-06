"""Pydantic schemas for the DetectionRule model."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator


def _coerce_uuid(v):
    """Convert UUID objects to strings before str validation."""
    return str(v) if isinstance(v, UUID) else v


class RuleCreate(BaseModel):
    """Input schema for creating or updating a rule.

    conditions is a JSON dict with the detection logic.
    Example: {"field": "event_type", "operator": "eq", "value": "auth_failure"}
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
    """Output schema with database fields."""

    id: Annotated[str, BeforeValidator(_coerce_uuid)]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
