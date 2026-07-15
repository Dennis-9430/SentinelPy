"""Modelo de evento de seguridad normalizado.

Representa un log ya procesado y convertido al Modelo de Información Común (CIM).
Cada fila es un evento individual con campos normalizados para búsqueda y correlación.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class NormalizedEvent(Base, TimestampMixin, UUIDMixin):
    """Evento de seguridad normalizado — la unidad básica del SIEM.

    Un evento puede venir de un syslog, un archivo de log, o un agente remoto.
    El parser se encarga de convertir el log crudo a este formato estándar.
    """

    __tablename__ = "events"

    # ── Metadatos de origen ──────────────────────────────────────────────
    source: Mapped[str] = mapped_column(
        String(255),
        index=True,
        comment="Identificador del origen (ej: servidor-web-01, firewall-panel)",
    )
    collector_type: Mapped[str] = mapped_column(
        String(50),
        comment="Tipo de colector que ingirió el evento: syslog, file, agent",
    )

    # ── Timestamp del evento (no confundir con created_at) ───────────────
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        comment="Timestamp del log original (no cuándo lo ingirió SentinelPy)",
    )

    # ── Campos normalizados (Common Information Model) ───────────────────
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

    # ── Campos de red ────────────────────────────────────────────────────
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

    # ── Campos de entidad ────────────────────────────────────────────────
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

    # ── Log crudo original ───────────────────────────────────────────────
    raw_log: Mapped[str | None] = mapped_column(
        Text,
        comment="Log original sin procesar, para forensia",
    )

    # ── Datos de análisis ─────────────────────────────────────────────────
    analysis_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Resultados de análisis: z-scores, ML scores, etc.",
    )

    # ── Índices compuestos para consultas frecuentes ─────────────────────
    __table_args__ = (
        Index("ix_events_event_timestamp_desc", event_timestamp.desc()),
        Index("ix_events_source_event_type", source, event_type),
        Index("ix_events_severity_timestamp", severity, event_timestamp),
        Index("ix_events_type_timestamp", event_type, event_timestamp),
    )
