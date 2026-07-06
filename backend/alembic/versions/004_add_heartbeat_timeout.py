"""Agregar heartbeat_timeout_minutes a agents

Revisión ID: 004
Depende de: 003
"""

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    """Agrega columna heartbeat_timeout_minutes con default 5."""
    op.add_column(
        "agents",
        sa.Column(
            "heartbeat_timeout_minutes",
            sa.Integer,
            nullable=False,
            server_default=sa.text("5"),
            comment="Minutos sin heartbeat antes de desactivar automáticamente",
        ),
    )


def downgrade() -> None:
    """Elimina la columna heartbeat_timeout_minutes (rollback)."""
    op.drop_column("agents", "heartbeat_timeout_minutes")
