"""Configuración de la aplicación usando pydantic-settings.

Las variables se cargan desde .env automáticamente.

Modos:
  - debug=True (default): desarrollo local, permite defaults
  - debug=False + DATABASE_URL con 'test': CI, permite defaults
  - debug=False + sin 'test': producción, SECRET_KEY y ADMIN_PASSWORD obligatorios
"""

import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Valores que NUNCA deben usarse en producción (used for rejection comparison only)
_INSECURE_DEFAULTS = {
    "secret_key": "05a0fb8849c109e045ed487f1e1975c056f6cf09368e90f35812ed986d671876",  # nosec B105
    "admin_password": "admin123",  # nosec B105
}


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
    # Producción: obligatorio; desarrollo/CI: permite defaults
    secret_key: str = "05a0fb8849c109e045ed487f1e1975c056f6cf09368e90f35812ed986d671876"
    access_token_expire_minutes: int = 480  # 8 horas
    jwt_algorithm: str = "HS256"

    # ── Admin seed ─────────────────────────────────────────────────────
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # ── Logging ─────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Colector syslog ──────────────────────────────────────────────────
    syslog_host: str = "0.0.0.0"  # nosec B104 — dev only; production overrides via env
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

    # ── Threat Intelligence ──────────────────────────────────────────────
    abuseipdb_api_key: str = ""
    virustotal_api_key: str = ""
    otx_api_key: str = ""
    ti_enrichment_enabled: bool = True
    ti_cache_ttl_minutes: int = 60

    # ── Análisis estadístico ────────────────────────────────────────────
    analysis_enabled: bool = True
    analysis_baseline_window_minutes: int = 60
    analysis_decay_rate: float = 0.5
    analysis_max_risk: float = 1.0

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        """En producción (debug=False, no test), verifica secrets seguros."""
        is_test = "test" in self.database_url.lower()
        is_production = not self.debug and not is_test

        if is_production:
            if not self.secret_key:
                raise ValueError(
                    "SECRET_KEY es obligatorio en producción. "
                    "Generá uno con: openssl rand -hex 32"
                )
            if self.secret_key == _INSECURE_DEFAULTS["secret_key"]:
                raise ValueError(
                    "SECRET_KEY es el valor por defecto — "
                    "generá uno nuevo con: openssl rand -hex 32"
                )
            if not self.admin_password:
                raise ValueError("ADMIN_PASSWORD es obligatorio en producción.")
            if self.admin_password == _INSECURE_DEFAULTS["admin_password"]:
                raise ValueError(
                    "ADMIN_PASSWORD es 'admin123' — "
                    "usá una contraseña segura en producción."
                )
        elif self.debug:
            # Desarrollo: advertir si se usan defaults inseguros
            if self.secret_key == _INSECURE_DEFAULTS["secret_key"]:
                logger.warning(
                    "⚠️  SECRET_KEY es el valor por defecto — "
                    "solo aceptable en desarrollo"
                )
            if self.admin_password == _INSECURE_DEFAULTS["admin_password"]:
                logger.warning(
                    "⚠️  ADMIN_PASSWORD es 'admin123' — solo aceptable en desarrollo"
                )
        return self

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # ── API key masking ──────────────────────────────────────────────────
    _API_KEY_FIELDS = ("abuseipdb_api_key", "virustotal_api_key", "otx_api_key")

    def __repr__(self) -> str:
        """Máscara de API keys en el repr para evitar logging de secretos."""
        parts = []
        for field in type(self).model_fields:
            value = getattr(self, field)
            if field in self._API_KEY_FIELDS:
                if value:
                    value = f"{value[:4]}***{value[-4:]}" if len(value) > 8 else "***"
                else:
                    value = ""
            parts.append(f"{field}={value!r}")
        return f"Settings({', '.join(parts)})"


# Instancia global de configuración — se importa donde se necesite
settings = Settings()
