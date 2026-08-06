"""Remote agent model for authenticated event ingestion.

Each agent has a unique API key (hashed with bcrypt) that allows
authentication via Bearer token on the v2 ingestion endpoints.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Agent(Base):
    """Remote agent authorized to send events to the system.

    Each agent represents a remote host that monitors local logs
    and forwards them to the SentinelPy server. It authenticates via
    API key (Bearer token) hashed with bcrypt — never stored in plaintext.

    Attributes:
        id: Unique autoincremental identifier.
        name: Unique agent name (logical identifier).
        hostname: Hostname of the machine where the agent runs.
        api_key_hash: Bcrypt hash of the agent's API key.
        last_seen: Last heartbeat received (UTC).
        active: Whether the agent is enabled to send events.
        version: Agent software version (optional).
        heartbeat_timeout_minutes: Minutes without heartbeat before automatically deactivating (default 5).
    """

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        comment="Nombre único del agente",
    )
    hostname: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Hostname del equipo del agente",
    )
    api_key_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Hash bcrypt de la API key",
    )
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Último heartbeat recibido (UTC)",
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Si el agente está habilitado",
    )
    version: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Versión del software agente",
    )
    heartbeat_timeout_minutes: Mapped[int] = mapped_column(
        default=5,
        server_default=text("5"),
        comment="Minutos sin heartbeat antes de desactivar automáticamente",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
