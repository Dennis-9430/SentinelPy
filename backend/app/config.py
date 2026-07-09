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
    # En producción cambiar con: openssl rand -hex 32
    secret_key: str = "05a0fb8849c109e045ed487f1e1975c056f6cf09368e90f35812ed986d671876"
    access_token_expire_minutes: int = 480  # 8 horas
    jwt_algorithm: str = "HS256"

    # ── Admin seed ─────────────────────────────────────────────────────
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # ── Logging ─────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Colector syslog ──────────────────────────────────────────────────
    syslog_host: str = "0.0.0.0"  # Escucha en todas las interfaces
    syslog_port: int = 5140  # Puerto no privilegiado (el 514 requiere sudo)

    # ── Notificaciones Email ────────────────────────────────────────────
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    notify_to: list[str] = []

    # ── Notificaciones Webhook ──────────────────────────────────────────
    webhook_url: str = ""
    notify_min_severity: str = "high"  # critical | high | medium | low

    # ── Análisis estadístico (Slice 1) ────────────────────────────────────
    analysis_enabled: bool = True
    analysis_baseline_window_minutes: int = 60
    analysis_decay_rate: float = 0.5
    analysis_max_risk: float = 1.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Instancia global de configuración — se importa donde se necesite
settings = Settings()
