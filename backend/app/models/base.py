"""Declarative base and mixins shared by all models.

SQLAlchemy 2.0 uses DeclarativeBase instead of declarative_base().
The mixins are inherited by every model to avoid repeating code.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models.

    SQLAlchemy looks up this class to register table metadata.
    """

    pass


class TimestampMixin:
    """Adds created_at and updated_at columns to any model.

    - created_at: set once when the record is created
    - updated_at: updated automatically on every modification
    - Both use UTC for consistency across time zones
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
    """Adds a UUID as the primary key.

    Advantages over an autoincrement integer:
    - Does not expose the number of records (security)
    - Can be generated on the client side
    - Works in distributed systems
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
