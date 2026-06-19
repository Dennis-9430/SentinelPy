"""Correlation rule model (Sigma-compatible format)."""

import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDMixin


class DetectionRule(Base, TimestampMixin, UUIDMixin):
    """A detection rule loosely based on the Sigma rule format."""

    __tablename__ = "rules"

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(20), default="medium")  # critical, high, medium, low, info
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, disabled, test

    # Rule logic: JSON defining conditions (e.g. {"field": "event_type", "operator": "eq", "value": "process_create"})
    conditions: Mapped[dict] = mapped_column(JSON)
    # Optional: correlation window in seconds (for multi-event rules)
    correlation_window: Mapped[int | None] = mapped_column(default=None)

    # Action on match
    alert_title: Mapped[str] = mapped_column(String(255))
    alert_severity: Mapped[str] = mapped_column(String(20), default="medium")

    # Metadata
    tags: Mapped[list] = mapped_column(JSON, default=list)
    references: Mapped[list] = mapped_column(JSON, default=list)
    false_positives: Mapped[str | None] = mapped_column(Text)
