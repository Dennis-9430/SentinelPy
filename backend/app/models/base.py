"""Base declarativa y mixins compartidos por todos los modelos.

SQLAlchemy 2.0 usa DeclarativeBase en lugar de declarative_base().
Los mixins se heredan en cada modelo para evitar repetir código.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Clase base para todos los modelos.

    SQLAlchemy busca esta clase para registrar metadatos de tablas.
    """

    pass


class TimestampMixin:
    """Agrega columnas created_at y updated_at a cualquier modelo.

    - created_at: se setea una sola vez al crear el registro
    - updated_at: se actualiza automáticamente en cada modificación
    - Ambos usan UTC para consistencia entre zonas horarias
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class UUIDMixin:
    """Agrega un UUID como clave primaria.

    Ventajas sobre autoincrement integer:
    - No expone cantidad de registros (seguridad)
    - Se puede generar del lado del cliente
    - Funciona en sistemas distribuidos
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
