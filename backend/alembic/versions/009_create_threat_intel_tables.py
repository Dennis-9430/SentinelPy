"""Crear tablas threat_intel_feeds e ioc_entries para Threat Intelligence

Revision ID: 009
Depends on: 008
"""

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    """Crea tablas para feeds de TI y entries de IOC."""
    op.create_table(
        "threat_intel_feeds",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_name",
            sa.String(100),
            nullable=False,
            comment="Nombre del proveedor (abuseipdb, otx, virustotal)",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="Estado del feed: active, inactive, error",
        ),
        sa.Column(
            "last_sync",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp del último sync exitoso",
        ),
        sa.Column(
            "error_count",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Contador acumulado de errores del provider",
        ),
        sa.Column(
            "config",
            sa.JSON,
            nullable=True,
            comment="Configuración específica del provider",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "ioc_entries",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "indicator",
            sa.String(500),
            nullable=False,
            comment="Valor del indicador (IP, dominio, hash, URL)",
        ),
        sa.Column(
            "ioc_type",
            sa.String(20),
            nullable=False,
            comment="Tipo de IOC: ip, domain, hash, url",
        ),
        sa.Column(
            "provider",
            sa.String(50),
            nullable=False,
            comment="Proveedor que reportó el IOC",
        ),
        sa.Column(
            "confidence",
            sa.Integer,
            nullable=False,
            comment="Nivel de confianza (0-100)",
        ),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Primera vez que se observó este IOC",
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Última vez que se observó este IOC",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp de expiración del IOC en cache",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes for IOC lookups
    op.create_index("ix_ioc_entries_indicator", "ioc_entries", ["indicator"])
    op.create_index(
        "ix_ioc_entries_indicator_type",
        "ioc_entries",
        ["indicator", "ioc_type"],
    )
    op.create_index(
        "ix_ioc_entries_type_provider",
        "ioc_entries",
        ["ioc_type", "provider"],
    )


def downgrade() -> None:
    """Elimina tablas de Threat Intelligence."""
    op.drop_index("ix_ioc_entries_type_provider", "ioc_entries")
    op.drop_index("ix_ioc_entries_indicator_type", "ioc_entries")
    op.drop_index("ix_ioc_entries_indicator", "ioc_entries")
    op.drop_table("ioc_entries")
    op.drop_table("threat_intel_feeds")
