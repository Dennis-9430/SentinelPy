"""Modelo de alerta generada por el motor de correlación.

Cuando una DetectionRule matchea uno o más eventos, se crea una alerta.
Las alertas tienen un ciclo de vida: open → acknowledged → investigating → resolved.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Alert(Base, TimestampMixin, UUIDMixin):
    """Alerta generada por el motor de correlación.

    Representa un hallazgo de seguridad que necesita atención.
    Se relaciona con la regla que la disparó y contiene metadata
    sobre los eventos que la activaron.
    """

    __tablename__ = "alerts"

    # ── Relación con la regla ────────────────────────────────────────────
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rules.id"),
        index=True,
        comment="ID de la regla que generó esta alerta",
    )

    # ── Información de la alerta ─────────────────────────────────────────
    title: Mapped[str] = mapped_column(
        String(255),
        comment="Título descriptivo (se hereda de la regla pero puede personalizarse)",
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        index=True,
        comment="Severidad: critical, high, medium, low, info",
    )
    description: Mapped[str] = mapped_column(
        Text,
        comment="Descripción del incidente detectado",
    )

    # ── Ciclo de vida ────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20),
        default="open",
        index=True,
        comment=(
            "Estado del ciclo de vida: "
            "open → acknowledged → investigating → resolved | false_positive"
        ),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="Cuándo se resolvió la alerta",
    )

    # ── Contexto ─────────────────────────────────────────────────────────
    event_count: Mapped[int] = mapped_column(
        default=1,
        comment="Cantidad de eventos que dispararon esta alerta",
    )
    first_event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="Timestamp del primer evento en la ventana de correlación",
    )
    last_event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="Timestamp del último evento en la ventana de correlación",
    )

    # ── Resolución ───────────────────────────────────────────────────────
    resolution_notes: Mapped[str | None] = mapped_column(
        Text,
        comment="Notas del analista sobre la resolución",
    )

    # ── Agrupación ─────────────────────────────────────────────────────
    group_key: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True,
        comment="Clave de agrupación (rule_id:source_ip)",
    )
    group_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Nombre legible del grupo de alertas",
    )
    risk_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Score de riesgo de la entidad (0.0-1.0) copiado del EntityRiskStore",
    )
