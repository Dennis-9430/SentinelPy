"""Modelo de agente remoto para ingesta autenticada de eventos.

Cada agente tiene una API key única (hasheada con bcrypt) que permite
autenticarse via Bearer token en los endpoints de ingesta v2.
"""

from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Agent(Base):
    """Agente remoto autorizado para enviar eventos al sistema.

    Cada agente representa un host remoto que monitorea logs locales
    y los reenvía al servidor SentinelPy. Se autentica via API key
    (Bearer token) hasheada con bcrypt — nunca se almacena plaintext.

    Attributes:
        id: Identificador único autoincremental.
        name: Nombre único del agente (identificador lógico).
        hostname: Hostname del equipo donde corre el agente.
        api_key_hash: Hash bcrypt de la API key del agente.
        last_seen: Último heartbeat recibido (UTC).
        active: Si el agente está habilitado para enviar eventos.
        version: Versión del software agente (opcional).
        heartbeat_timeout_minutes: Minutos sin heartbeat antes de desactivar automáticamente (default 5).
    """

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False,
        comment="Nombre único del agente",
    )
    hostname: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Hostname del equipo del agente",
    )
    api_key_hash: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Hash bcrypt de la API key",
    )
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Último heartbeat recibido (UTC)",
    )
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Si el agente está habilitado",
    )
    version: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="Versión del software agente",
    )
    heartbeat_timeout_minutes: Mapped[int] = mapped_column(
        default=5, server_default=text("5"),
        comment="Minutos sin heartbeat antes de desactivar automáticamente",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
