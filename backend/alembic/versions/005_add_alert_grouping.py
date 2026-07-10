"""Agregar columnas de agrupación a alerts

Revisión ID: 005
Depende de: 004
"""

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    """Agrega columnas group_key, group_name y risk_score a alerts."""
    op.add_column(
        "alerts",
        sa.Column(
            "group_key",
            sa.String(255),
            nullable=True,
            comment="Clave de agrupación (rule_id:source_ip)",
        ),
    )
    op.create_index("ix_alerts_group_key", "alerts", ["group_key"])

    op.add_column(
        "alerts",
        sa.Column(
            "group_name",
            sa.String(255),
            nullable=True,
            comment="Nombre legible del grupo de alertas",
        ),
    )

    op.add_column(
        "alerts",
        sa.Column(
            "risk_score",
            sa.Float,
            nullable=True,
            comment="Score de riesgo de la entidad (0.0-1.0)",
        ),
    )


def downgrade() -> None:
    """Elimina las columnas de agrupación (rollback)."""
    op.drop_index("ix_alerts_group_key", table_name="alerts")
    op.drop_column("alerts", "risk_score")
    op.drop_column("alerts", "group_name")
    op.drop_column("alerts", "group_key")
