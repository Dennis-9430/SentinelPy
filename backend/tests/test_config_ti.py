"""Tests for TI configuration fields in Settings.

Covers: TI API keys load without error, defaults correct,
ti_enrichment_enabled defaults True, API keys masked in repr.
"""

import pytest


class TestTIConfigDefaults:
    def test_empty_api_keys_load_without_error(self):
        """Settings with empty TI API keys instantiates without error."""
        from app.config import Settings

        s = Settings(
            abuseipdb_api_key="",
            virustotal_api_key="",
            otx_api_key="",
        )
        assert s.abuseipdb_api_key == ""
        assert s.virustotal_api_key == ""
        assert s.otx_api_key == ""

    def test_ti_enrichment_enabled_defaults_true(self):
        """ti_enrichment_enabled defaults to True when not specified."""
        from app.config import Settings

        s = Settings()
        assert s.ti_enrichment_enabled is True

    def test_ti_cache_ttl_minutes_defaults_60(self):
        """ti_cache_ttl_minutes defaults to 60 when not specified."""
        from app.config import Settings

        s = Settings()
        assert s.ti_cache_ttl_minutes == 60

    def test_ti_config_fields_can_be_overridden(self):
        """TI config fields can be overridden with custom values."""
        from app.config import Settings

        s = Settings(
            abuseipdb_api_key="test_key_123",
            virustotal_api_key="vt_key_456",
            otx_api_key="otx_key_789",
            ti_enrichment_enabled=False,
            ti_cache_ttl_minutes=30,
        )
        assert s.abuseipdb_api_key == "test_key_123"
        assert s.virustotal_api_key == "vt_key_456"
        assert s.otx_api_key == "otx_key_789"
        assert s.ti_enrichment_enabled is False
        assert s.ti_cache_ttl_minutes == 30


class TestTIConfigRepr:
    def test_repr_masks_long_api_key(self):
        """API keys longer than 8 chars show first 4 and last 4 with ***."""
        from app.config import Settings

        s = Settings(abuseipdb_api_key="abcdefghijklmnop")
        r = repr(s)
        assert "abcd***mnop" in r
        assert "abcdefghijklmnop" not in r

    def test_repr_masks_short_api_key(self):
        """Short API keys (<=8 chars) show *** only."""
        from app.config import Settings

        s = Settings(abuseipdb_api_key="short")
        r = repr(s)
        assert "***" in r
        assert "short" not in r

    def test_repr_empty_key_shows_empty_string(self):
        """Empty API key shows empty string in repr."""
        from app.config import Settings

        s = Settings(abuseipdb_api_key="")
        r = repr(s)
        assert "abuseipdb_api_key=''" in r
