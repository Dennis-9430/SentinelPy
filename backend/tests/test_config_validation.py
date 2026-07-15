"""Tests for config.py — 82% coverage.

Covers: _validate_production_secrets paths (production, debug, test mode).
"""

import logging

import pytest


class TestProductionValidation:
    def test_production_with_insecure_secret_key(self):
        """Production mode + default secret_key raises ValueError."""
        with pytest.raises(ValueError, match="SECRET_KEY es el valor por defecto"):
            from app.config import Settings

            Settings(
                debug=False,
                database_url="postgresql+asyncpg://user:pass@host:5432/prod_db",
                secret_key="05a0fb8849c109e045ed487f1e1975c056f6cf09368e90f35812ed986d671876",
                admin_password="secure_password_123",
            )

    def test_production_with_insecure_admin_password(self):
        """Production mode + default admin password raises ValueError."""
        with pytest.raises(ValueError, match="ADMIN_PASSWORD es 'admin123'"):
            from app.config import Settings

            Settings(
                debug=False,
                database_url="postgresql+asyncpg://user:pass@host:5432/prod_db",
                secret_key="a_secure_secret_key_that_is_definitely_not_default_12345678",
                admin_password="admin123",
            )

    def test_production_with_empty_secret_key(self):
        """Production mode + empty secret_key raises ValueError."""
        with pytest.raises(ValueError, match="SECRET_KEY es obligatorio"):
            from app.config import Settings

            Settings(
                debug=False,
                database_url="postgresql+asyncpg://user:pass@host:5432/prod_db",
                secret_key="",
                admin_password="secure_pass",
            )

    def test_production_with_empty_admin_password(self):
        """Production mode + empty admin_password raises ValueError."""
        with pytest.raises(ValueError, match="ADMIN_PASSWORD es obligatorio"):
            from app.config import Settings

            Settings(
                debug=False,
                database_url="postgresql+asyncpg://user:pass@host:5432/prod_db",
                secret_key="a_secure_secret_key_that_is_definitely_not_default_12345678",
                admin_password="",
            )

    def test_production_with_valid_secrets(self):
        """Production mode with secure secrets passes validation."""
        from app.config import Settings

        s = Settings(
            debug=False,
            database_url="postgresql+asyncpg://user:pass@host:5432/prod_db",
            secret_key="a_secure_secret_key_that_is_definitely_not_default_12345678",
            admin_password="a_very_strong_password_456",
        )
        assert s.debug is False

    def test_test_mode_allows_insecure_defaults(self):
        """Test mode (database_url contains 'test') allows defaults."""
        from app.config import Settings

        s = Settings(
            debug=False,
            database_url="postgresql+asyncpg://user:pass@host:5432/test_db",
        )
        assert s.secret_key  # default allowed in test mode


class TestDebugWarnings:
    def test_debug_default_secret_warns(self, caplog):
        """Debug mode with default secret_key logs a warning."""
        from app.config import Settings

        with caplog.at_level(logging.WARNING):
            Settings(
                debug=True,
                secret_key="05a0fb8849c109e045ed487f1e1975c056f6cf09368e90f35812ed986d671876",
            )
        assert any(
            "SECRET_KEY es el valor por defecto" in r.message for r in caplog.records
        )

    def test_debug_default_admin_password_warns(self, caplog):
        """Debug mode with default admin_password logs a warning."""
        from app.config import Settings

        with caplog.at_level(logging.WARNING):
            Settings(
                debug=True,
                admin_password="admin123",
            )
        assert any("ADMIN_PASSWORD es 'admin123'" in r.message for r in caplog.records)

    def test_debug_secure_secrets_no_warning(self, caplog):
        """Debug mode with secure secrets does NOT warn."""
        from app.config import Settings

        with caplog.at_level(logging.WARNING):
            Settings(
                debug=True,
                secret_key="a_secure_secret_key_12345678901234567890",
                admin_password="a_strong_pass_123",
            )
        secret_warnings = [
            r
            for r in caplog.records
            if "SECRET_KEY es el valor por defecto" in r.message
        ]
        assert len(secret_warnings) == 0
