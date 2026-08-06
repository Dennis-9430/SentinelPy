"""System user model for authentication and roles."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class User(Base, TimestampMixin, UUIDMixin):
    """System user for authentication and access control.

    Each user has a unique name, a bcrypt-hashed password,
    a role (admin/analyst) and an active field to enable/disable them.
    """

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        comment="Nombre de usuario único para login",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        comment="Password hasheada con bcrypt",
    )
    role: Mapped[str] = mapped_column(
        String(20),
        default="analyst",
        comment="Rol: admin | analyst",
    )
    active: Mapped[bool] = mapped_column(
        default=True,
        comment="Si el usuario está habilitado",
    )
