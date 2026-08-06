"""Models for Threat Intelligence.

ThreatIntelFeed: registers feeds from TI providers (AbuseIPDB, OTX, VT).
IOCEntry: stores queried indicators of compromise (IOCs).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ThreatIntelFeed(UUIDMixin, TimestampMixin, Base):
    """Record of a Threat Intelligence feed.

    Stores the status of each provider (active/inactive/error),
    the last successful sync, and provider-specific configuration.
    """

    __tablename__ = "threat_intel_feeds"

    provider_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Nombre del proveedor (abuseipdb, otx, virustotal)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Estado del feed: active, inactive, error",
    )

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        now = datetime.now(UTC)
        if self.id is None:
            self.id = uuid.uuid4()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now
        if self.status is None:
            self.status = "active"
        if self.error_count is None:
            self.error_count = 0
    last_sync: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp del último sync exitoso",
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Contador acumulado de errores del provider",
    )
    config: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Configuración específica del provider (JSON)",
    )


class IOCEntry(UUIDMixin, TimestampMixin, Base):
    """Indicator of Compromise (IOC) entry.

    Stores each queried IOC with its type, provider,
    confidence level, and observation windows.
    """

    __tablename__ = "ioc_entries"

    indicator: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Valor del indicador (IP, dominio, hash, URL)",
    )
    ioc_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Tipo de IOC: ip, domain, hash, url",
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Proveedor que reportó el IOC",
    )
    confidence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Nivel de confianza (0-100)",
    )
    first_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Primera vez que se observó este IOC",
    )
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Última vez que se observó este IOC",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp de expiración del IOC en cache",
    )

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        now = datetime.now(UTC)
        if self.id is None:
            self.id = uuid.uuid4()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now
