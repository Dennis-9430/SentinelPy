"""Normalized security event model."""

import uuid
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDMixin


class NormalizedEvent(Base, TimestampMixin, UUIDMixin):
    """A single normalized security event (log line after parsing)."""

    __tablename__ = "events"

    # Source metadata
    source: Mapped[str] = mapped_column(String(255), index=True)
    collector_type: Mapped[str] = mapped_column(String(50))  # syslog, file, agent

    # Timestamp from the log itself (not ingestion time)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # Normalized fields (Common Information Model)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)  # critical, high, medium, low, info
    description: Mapped[str] = mapped_column(Text)

    # Entity fields
    source_ip: Mapped[str | None] = mapped_column(String(45))
    destination_ip: Mapped[str | None] = mapped_column(String(45))
    source_port: Mapped[int | None] = mapped_column(Integer)
    destination_port: Mapped[int | None] = mapped_column(Integer)
    protocol: Mapped[str | None] = mapped_column(String(20))
    user_name: Mapped[str | None] = mapped_column(String(255))
    process_name: Mapped[str | None] = mapped_column(String(255))
    file_path: Mapped[str | None] = mapped_column(Text)

    # Raw log for forensic reference
    raw_log: Mapped[str | None] = mapped_column(Text)

    # Full-text search index
    __table_args__ = (
        Index("ix_events_event_timestamp_desc", event_timestamp.desc()),
        Index("ix_events_source_event_type", source, event_type),
    )
