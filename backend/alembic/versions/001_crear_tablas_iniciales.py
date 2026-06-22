"""Crear tablas iniciales: events, rules, alerts

Revisión ID: 001
Crea: (ninguna, es la primera migración)
"""

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    """Crea las tablas events, rules y alerts."""

    # ── Tabla: events ────────────────────────────────────────────────────
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(255), nullable=False, index=True),
        sa.Column("collector_type", sa.String(50), nullable=False),
        sa.Column(
            "event_timestamp", sa.DateTime(timezone=True),
            nullable=False, index=True,
        ),
        sa.Column("event_type", sa.String(100), nullable=False, index=True),
        sa.Column("severity", sa.String(20), nullable=False, index=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("source_ip", sa.String(45), nullable=True),
        sa.Column("destination_ip", sa.String(45), nullable=True),
        sa.Column("source_port", sa.Integer, nullable=True),
        sa.Column("destination_port", sa.Integer, nullable=True),
        sa.Column("protocol", sa.String(20), nullable=True),
        sa.Column("user_name", sa.String(255), nullable=True),
        sa.Column("process_name", sa.String(255), nullable=True),
        sa.Column("file_path", sa.Text, nullable=True),
        sa.Column("raw_log", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )

    # Índices compuestos
    op.create_index("ix_events_event_timestamp_desc", "events", [sa.text("event_timestamp DESC")])
    op.create_index("ix_events_source_event_type", "events", ["source", "event_type"])

    # ── Tabla: rules ─────────────────────────────────────────────────────
    op.create_table(
        "rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("conditions", postgresql.JSON, nullable=False),
        sa.Column("correlation_window", sa.Integer, nullable=True),
        sa.Column("alert_title", sa.String(255), nullable=False),
        sa.Column("alert_severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("tags", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("references", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("false_positives", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )

    # ── Tabla: alerts ────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rules.id"), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, index=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open", index=True),
        sa.Column("event_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("first_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Elimina las tablas events, rules y alerts (rollback completo)."""
    op.drop_table("alerts")
    op.drop_table("rules")
    op.drop_table("events")
