"""Normalized security event model.

Represents a log already processed and converted to the Common Information Model (CIM).
Each row is an individual event with normalized fields for search and correlation.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class NormalizedEvent(Base, TimestampMixin, UUIDMixin):
    """Normalized security event — the basic unit of the SIEM.

    An event can come from syslog, a log file, or a remote agent.
    The parser converts the raw log into this standard format.
    """

    __tablename__ = "events"

    # ── Source metadata ──────────────────────────────────────────────────
    source: Mapped[str] = mapped_column(
        String(255),
        index=True,
        comment="Identificador del origen (ej: servidor-web-01, firewall-panel)",
    )
    collector_type: Mapped[str] = mapped_column(
        String(50),
        comment="Tipo de colector que ingirió el evento: syslog, file, agent",
    )

    # ── Event timestamp (do not confuse with created_at) ─────────────────
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        comment="Timestamp del log original (no cuándo lo ingirió SentinelPy)",
    )

    # ── Normalized fields (Common Information Model) ─────────────────────
    event_type: Mapped[str] = mapped_column(
        String(100),
        index=True,
        comment="Tipo de evento normalizado: process_create, auth_failure, port_scan, etc.",
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        index=True,
        comment="Severidad: critical, high, medium, low, info",
    )
    description: Mapped[str] = mapped_column(
        Text,
        comment="Descripción legible del evento",
    )

    # ── Network fields ───────────────────────────────────────────────────
    source_ip: Mapped[str | None] = mapped_column(
        String(45),
        index=True,
        comment="IP de origen (soporta IPv4 e IPv6)",
    )
    destination_ip: Mapped[str | None] = mapped_column(
        String(45),
        comment="IP de destino",
    )
    source_port: Mapped[int | None] = mapped_column(
        Integer,
        comment="Puerto de origen",
    )
    destination_port: Mapped[int | None] = mapped_column(
        Integer,
        comment="Puerto de destino",
    )
    protocol: Mapped[str | None] = mapped_column(
        String(20),
        comment="Protocolo de red: TCP, UDP, ICMP, etc.",
    )

    # ── Entity fields ────────────────────────────────────────────────────
    user_name: Mapped[str | None] = mapped_column(
        String(255),
        comment="Nombre de usuario involucrado (si aplica)",
    )
    process_name: Mapped[str | None] = mapped_column(
        String(255),
        comment="Nombre del proceso (ej: powershell.exe, nginx)",
    )
    file_path: Mapped[str | None] = mapped_column(
        Text,
        comment="Ruta de archivo involucrada (si aplica)",
    )

    # ── Original raw log ─────────────────────────────────────────────────
    raw_log: Mapped[str | None] = mapped_column(
        Text,
        comment="Log original sin procesar, para forensia",
    )

    # ── Analysis data ────────────────────────────────────────────────────
    analysis_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Resultados de análisis: z-scores, ML scores, etc.",
    )

    # ── Composite indexes for frequent queries ───────────────────────────
    __table_args__ = (
        Index("ix_events_event_timestamp_desc", event_timestamp.desc()),
        Index("ix_events_source_event_type", source, event_type),
        Index("ix_events_severity_timestamp", severity, event_timestamp),
        Index("ix_events_type_timestamp", event_type, event_timestamp),
    )
