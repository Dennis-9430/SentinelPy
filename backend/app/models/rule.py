"""Modelo de regla de detección (compatible con formato Sigma).

Las reglas definen condiciones que, al cumplirse, generan alertas.
Siguen una estructura inspirada en Sigma, el estándar abierto para reglas SIEM.
"""

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class DetectionRule(Base, TimestampMixin, UUIDMixin):
    """Regla de detección — define QUÉ buscar y QUÉ alerta generar.

    Cada regla tiene condiciones (expresadas como JSON) que el motor de
    correlación evalúa contra cada evento entrante.
    """

    __tablename__ = "rules"

    # ── Identificación ───────────────────────────────────────────────────
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

    # ── Clasificación ────────────────────────────────────────────────────
    severity: Mapped[str] = mapped_column(
        String(20),
        default="medium",
        comment="Severidad de la regla: critical, high, medium, low, info",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        comment="Estado: active (activa), disabled (desactivada), test (solo logging)",
    )

    # ── Lógica de detección ──────────────────────────────────────────────
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

    # ── Alerta a generar ─────────────────────────────────────────────────
    alert_title: Mapped[str] = mapped_column(
        String(255),
        comment="Título de la alerta que se crea cuando la regla matchea",
    )
    alert_severity: Mapped[str] = mapped_column(
        String(20),
        default="medium",
        comment="Severidad de la alerta generada",
    )

    # ── Metadatos ────────────────────────────────────────────────────────
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
