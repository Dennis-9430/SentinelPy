"""Generated alert model (result of rule match)."""

import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDMixin


class Alert(Base, TimestampMixin, UUIDMixin):
    """An alert generated when a DetectionRule matches events."""

    __tablename__ = "alerts"

    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rules.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(20), index=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open, acknowledged, investigating, resolved, false_positive
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Count of events that triggered this alert
    event_count: Mapped[int] = mapped_column(default=1)
    # First and last event timestamp in the correlation window
    first_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Resolution notes
    resolution_notes: Mapped[str | None] = mapped_column(Text)
