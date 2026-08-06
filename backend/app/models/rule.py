"""Detection rule model (compatible with the Sigma format).

Rules define conditions that, when met, generate alerts.
They follow a structure inspired by Sigma, the open standard for SIEM rules.
"""

from sqlalchemy import JSON, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class DetectionRule(Base, TimestampMixin, UUIDMixin):
    """Detection rule — defines WHAT to look for and WHAT alert to generate.

    Each rule has conditions (expressed as JSON) that the correlation
    engine evaluates against every incoming event.
    """

    __tablename__ = "rules"

    # ── Identification ───────────────────────────────────────────────────
    title: Mapped[str] = mapped_column(
        String(255),
        comment="Título descriptivo de la regla (ej: 'Detección de fuerza bruta SSH')",
    )
    description: Mapped[str] = mapped_column(
        Text,
        comment="Descripción detallada: qué detecta, por qué es relevante",
    )
    author: Mapped[str | None] = mapped_column(
        String(255),
        comment="Autor de la regla",
    )

    # ── Classification ───────────────────────────────────────────────────
    severity: Mapped[str] = mapped_column(
        String(20),
        default="medium",
        comment="Severidad de la regla: critical, high, medium, low, info",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        index=True,
        comment="Estado: active (activa), disabled (desactivada), test (solo logging)",
    )

    # ── Detection logic ──────────────────────────────────────────────────
    conditions: Mapped[dict] = mapped_column(
        JSON,
        comment=(
            "Condiciones en JSON. "
            'Ej: {"field": "event_type", "operator": "eq", "value": "process_create"}'
        ),
    )
    correlation_window: Mapped[int | None] = mapped_column(
        default=None,
        comment=(
            "Ventana de correlación en segundos. "
            "Si se setea, la regla espera múltiples eventos en ese período."
        ),
    )

    # ── Alert to generate ────────────────────────────────────────────────
    alert_title: Mapped[str] = mapped_column(
        String(255),
        comment="Título de la alerta que se crea cuando la regla matchea",
    )
    alert_severity: Mapped[str] = mapped_column(
        String(20),
        default="medium",
        comment="Severidad de la alerta generada",
    )

    # ── Metadata ─────────────────────────────────────────────────────────
    tags: Mapped[list] = mapped_column(
        JSON,
        default=list,
        comment="Etiquetas para categorizar la regla (ej: ['attack.t1078', 'mitre.credential-access'])",
    )
    references: Mapped[list] = mapped_column(
        JSON,
        default=list,
        comment="URLs de referencia (CVE, artículos, documentación)",
    )
    false_positives: Mapped[str | None] = mapped_column(
        Text,
        comment="Casos conocidos de falsos positivos",
    )

    # ── Composite indexes for frequent queries ───────────────────────────
    __table_args__ = (Index("ix_rules_status_severity", "status", "severity"),)
