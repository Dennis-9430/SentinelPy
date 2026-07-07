"""Modelo de usuario del sistema para autenticación y roles."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class User(Base, TimestampMixin, UUIDMixin):
    """Usuario del sistema para autenticación y control de acceso.

    Cada usuario tiene un nombre único, password hasheada con bcrypt,
    un rol (admin/analyst) y un campo active para habilitar/deshabilitar.
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
