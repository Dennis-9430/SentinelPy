"""Crear tabla entity_risks para análisis de riesgo por entidad

Revision ID: 007
Depends on: 006
"""

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    """Crea la tabla entity_risks con PK entity_key."""
    op.create_table(
        "entity_risks",
        sa.Column("entity_key", sa.String(255), primary_key=True),
        sa.Column(
            "risk_score", sa.Float, nullable=False, server_default="0.0",
            comment="Score de riesgo acumulado (0.0-1.0)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Última actualización del score",
        ),
    )


def downgrade() -> None:
    """Elimina la tabla entity_risks."""
    op.drop_table("entity_risks")
