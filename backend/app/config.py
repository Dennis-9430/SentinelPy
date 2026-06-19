"""Configuración de la aplicación usando pydantic-settings.

Las variables se cargan desde .env automáticamente.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuración general de SentinelPy.

    Todas las variables pueden sobreescribirse con un archivo .env
    o variables de entorno del sistema.
    """

    # ── Información de la app ────────────────────────────────────────────
    app_name: str = "SentinelPy"
    app_version: str = "0.1.0"
    debug: bool = True

    # ── Base de datos ────────────────────────────────────────────────────
    # Formato: postgresql+asyncpg://usuario:password@host:puerto/database
    database_url: str = (
        "postgresql+asyncpg://sentinel:sentinel_dev@localhost:5432/sentinelpy"
    )

    # ── Seguridad ────────────────────────────────────────────────────────
    # En producción cambiar con un secreto generado con: openssl rand -hex 32
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30

    # ── Colector syslog ──────────────────────────────────────────────────
    syslog_host: str = "0.0.0.0"  # Escucha en todas las interfaces
    syslog_port: int = 5140       # Puerto no privilegiado (el 514 requiere sudo)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Instancia global de configuración — se importa donde se necesite
settings = Settings()
