"""Agregar columna analysis_data a events

Revision ID: 006
Depends on: 005
"""

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade() -> None:
    """Agrega columna analysis_data (JSONB) a events para análisis ML."""
    op.add_column(
        "events",
        sa.Column(
            "analysis_data",
            JSONB,
            nullable=True,
            comment="Datos de análisis ML (z-score, anomaly score)",
        ),
    )


def downgrade() -> None:
    """Elimina columna analysis_data."""
    op.drop_column("events", "analysis_data")
