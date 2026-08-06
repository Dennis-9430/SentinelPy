"""Application configuration using pydantic-settings.

Variables are loaded from .env automatically.

Modes:
  - debug=True (default): local development, allows defaults
  - debug=False + DATABASE_URL containing 'test': CI, allows defaults
  - debug=False + no 'test': production, SECRET_KEY and ADMIN_PASSWORD required
"""

import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Values that must NEVER be used in production (used for rejection comparison only)
_INSECURE_DEFAULTS = {
    "secret_key": "05a0fb8849c109e045ed487f1e1975c056f6cf09368e90f35812ed986d671876",  # nosec B105
    "admin_password": "admin123",  # nosec B105
}


class Settings(BaseSettings):
    """General SentinelPy configuration.

    All variables can be overridden with a .env file
    or system environment variables.
    """

    # ── App information ────────────────────────────────────────────
    app_name: str = "SentinelPy"
    app_version: str = "0.1.0"
    debug: bool = True

    # ── Database ────────────────────────────────────────────────────
    # Format: postgresql+asyncpg://user:password@host:port/database
    database_url: str = (
        "postgresql+asyncpg://sentinel:sentinel_dev@localhost:5432/sentinelpy"
    )

    # ── Security ────────────────────────────────────────────────────────
    # In production, change with: openssl rand -hex 32
    # Production: required; development/CI: allows defaults
    secret_key: str = "05a0fb8849c109e045ed487f1e1975c056f6cf09368e90f35812ed986d671876"
    access_token_expire_minutes: int = 480  # 8 horas
    jwt_algorithm: str = "HS256"

    # ── Admin seed ─────────────────────────────────────────────────────
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # ── Logging ─────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Syslog collector ──────────────────────────────────────────────────
    syslog_host: str = "0.0.0.0"  # nosec B104 — dev only; production overrides via env
    syslog_port: int = 5140      # Non-privileged port (514 requires sudo)

    # ── Email notifications ────────────────────────────────────────────
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    notify_to: list[str] = []

    # ── Webhook notifications ──────────────────────────────────────────
    webhook_url: str = ""
    notify_min_severity: str = "high"  # critical | high | medium | low

    # ── Threat Intelligence ──────────────────────────────────────────────
    abuseipdb_api_key: str = ""
    virustotal_api_key: str = ""
    otx_api_key: str = ""
    ti_enrichment_enabled: bool = True
    ti_cache_ttl_minutes: int = 60

    # ── Statistical analysis ────────────────────────────────────────────
    analysis_enabled: bool = True
    analysis_baseline_window_minutes: int = 60
    analysis_decay_rate: float = 0.5
    analysis_max_risk: float = 1.0

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        """In production (debug=False, no test), verifies secure secrets."""
        is_test = "test" in self.database_url.lower()
        is_production = not self.debug and not is_test

        if is_production:
            if not self.secret_key:
                raise ValueError(
                    "SECRET_KEY is required in production. "
                    "Generate one with: openssl rand -hex 32"
                )
            if self.secret_key == _INSECURE_DEFAULTS["secret_key"]:
                raise ValueError(
                    "SECRET_KEY is the default value — "
                    "generate a new one with: openssl rand -hex 32"
                )
            if not self.admin_password:
                raise ValueError("ADMIN_PASSWORD is required in production.")
            if self.admin_password == _INSECURE_DEFAULTS["admin_password"]:
                raise ValueError(
                    "ADMIN_PASSWORD is 'admin123' — "
                    "use a secure password in production."
                )
        elif self.debug:
            # Development: warn if insecure defaults are used
            if self.secret_key == _INSECURE_DEFAULTS["secret_key"]:
                logger.warning(
                    "⚠️  SECRET_KEY is the default value — "
                    "only acceptable in development"
                )
            if self.admin_password == _INSECURE_DEFAULTS["admin_password"]:
                logger.warning(
                    "⚠️  ADMIN_PASSWORD is 'admin123' — only acceptable in development"
                )
        return self

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # ── API key masking ──────────────────────────────────────────────────
    _API_KEY_FIELDS = ("abuseipdb_api_key", "virustotal_api_key", "otx_api_key")

    def __repr__(self) -> str:
        """Mask API keys in the repr to avoid logging secrets."""
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


# Global config instance — imported wherever needed
settings = Settings()
