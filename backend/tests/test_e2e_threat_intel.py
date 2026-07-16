"""End-to-end tests for Threat Intelligence enrichment flow.

Tests the full pipeline:
- Event with source_ip → enrichment writes analysis_data["ti"]
- Empty API keys → no enrichment, no errors
"""

import pytest
import pytest_asyncio

from app.services.ti_providers.base import IOCResult
from app.services.threat_intel_service import ThreatIntelService


# ── Helpers ───────────────────────────────────────────────────────────────


def _event_with_ip(ip: str = "1.2.3.4") -> dict:
    """Create a base event dict with a source_ip."""
    return {
        "event_type": "authentication",
        "severity": "medium",
        "source": "ssh-server",
        "description": "Failed login attempt",
        "source_ip": ip,
        "destination_ip": "10.0.0.1",
        "event_timestamp": "2025-01-15T10:30:00Z",
    }


# ── Tests: Enrichment with active providers ───────────────────────────────


class TestEnrichmentFlow:
    @pytest.mark.asyncio
    async def test_enrich_event_with_known_ip(self):
        """Event with a known malicious IP gets enriched with TI data."""
        svc = ThreatIntelService()

        class MockProvider:
            name = "mock_ti"
            supported_types = ["ip"]

            async def lookup(self, indicator, ioc_type):
                if indicator == "1.2.3.4":
                    return IOCResult(
                        indicator="1.2.3.4",
                        ioc_type="ip",
                        confidence=90,
                        provider="mock_ti",
                    )
                return None

        svc.register_provider(MockProvider())
        event = _event_with_ip("1.2.3.4")
        result = await svc.enrich(event)

        assert "matches" in result
        assert len(result["matches"]) == 1
        match = result["matches"][0]
        assert match["indicator"] == "1.2.3.4"
        assert match["confidence"] == 90
        assert match["provider"] == "mock_ti"

    @pytest.mark.asyncio
    async def test_enrich_event_with_unknown_ip(self):
        """Event with an unknown IP returns no enrichment."""
        svc = ThreatIntelService()

        class MockProvider:
            name = "mock_ti"
            supported_types = ["ip"]

            async def lookup(self, indicator, ioc_type):
                return None

        svc.register_provider(MockProvider())
        event = _event_with_ip("10.0.0.99")
        result = await svc.enrich(event)

        assert result == {}

    @pytest.mark.asyncio
    async def test_enrich_event_no_source_ip(self):
        """Event without source_ip or destination_ip returns no enrichment."""
        svc = ThreatIntelService()

        class MockProvider:
            name = "mock_ti"
            supported_types = ["ip"]

            async def lookup(self, indicator, ioc_type):
                return IOCResult(
                    indicator=indicator,
                    ioc_type="ip",
                    confidence=80,
                    provider="mock_ti",
                )

        svc.register_provider(MockProvider())
        event = {
            "event_type": "authentication",
            "severity": "medium",
            "source": "ssh-server",
            "description": "No IPs in event",
        }
        result = await svc.enrich(event)
        assert result == {}

    @pytest.mark.asyncio
    async def test_enrich_event_both_ips(self):
        """Event with both source_ip and destination_ip checks both."""
        svc = ThreatIntelService()

        class MockProvider:
            name = "mock_ti"
            supported_types = ["ip"]
            looked_up = []

            async def lookup(self, indicator, ioc_type):
                self.looked_up.append(indicator)
                if indicator == "1.2.3.4":
                    return IOCResult(
                        indicator="1.2.3.4",
                        ioc_type="ip",
                        confidence=95,
                        provider="mock_ti",
                    )
                return None

        provider = MockProvider()
        svc.register_provider(provider)
        event = _event_with_ip("1.2.3.4")
        event["destination_ip"] = "5.6.7.8"
        result = await svc.enrich(event)

        assert "matches" in result
        assert len(result["matches"]) == 1
        assert result["matches"][0]["indicator"] == "1.2.3.4"
        # Both IPs should have been checked
        assert "1.2.3.4" in provider.looked_up
        assert "5.6.7.8" in provider.looked_up


# ── Tests: Disabled / no API keys ─────────────────────────────────────────


class TestEnrichmentDisabled:
    @pytest.mark.asyncio
    async def test_enrichment_disabled_returns_empty(self):
        """When ti_enrichment_enabled=False, enrichment returns empty dict."""
        from app.config import settings

        original = settings.ti_enrichment_enabled
        settings.ti_enrichment_enabled = False
        try:
            svc = ThreatIntelService()
            event = _event_with_ip("1.2.3.4")
            result = await svc.enrich(event)
            assert result == {}
        finally:
            settings.ti_enrichment_enabled = original

    @pytest.mark.asyncio
    async def test_lookup_disabled_returns_none(self):
        """When ti_enrichment_enabled=False, lookup returns None."""
        from app.config import settings

        original = settings.ti_enrichment_enabled
        settings.ti_enrichment_enabled = False
        try:
            svc = ThreatIntelService()

            class MockProvider:
                name = "mock_ti"
                supported_types = ["ip"]

                async def lookup(self, indicator, ioc_type):
                    return IOCResult(
                        indicator=indicator,
                        ioc_type="ip",
                        confidence=90,
                        provider="mock_ti",
                    )

            svc.register_provider(MockProvider())
            result = await svc.lookup("1.2.3.4", "ip")
            assert result is None
        finally:
            settings.ti_enrichment_enabled = original

    @pytest.mark.asyncio
    async def test_no_providers_returns_none(self):
        """When no providers registered, lookup returns None gracefully."""
        svc = ThreatIntelService()
        result = await svc.lookup("1.2.3.4", "ip")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_providers_enrich_returns_empty(self):
        """When no providers registered, enrich returns empty dict."""
        svc = ThreatIntelService()
        event = _event_with_ip("1.2.3.4")
        result = await svc.enrich(event)
        assert result == {}


# ── Tests: Cache behavior ─────────────────────────────────────────────────


class TestEnrichmentCaching:
    @pytest.mark.asyncio
    async def test_cached_result_returned_on_second_lookup(self):
        """Second lookup for same indicator returns cached result."""
        svc = ThreatIntelService()
        call_count = 0

        class MockProvider:
            name = "mock_ti"
            supported_types = ["ip"]

            async def lookup(self, indicator, ioc_type):
                nonlocal call_count
                call_count += 1
                return IOCResult(
                    indicator=indicator,
                    ioc_type="ip",
                    confidence=80,
                    provider="mock_ti",
                )

        svc.register_provider(MockProvider())

        await svc.lookup("1.2.3.4", "ip")
        assert call_count == 1

        result = await svc.lookup("1.2.3.4", "ip")
        assert call_count == 1  # Should not have called provider again
        assert result is not None
        assert result.indicator == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_enrich_uses_cache(self):
        """Enrichment benefits from cached lookup results."""
        svc = ThreatIntelService()
        call_count = 0

        class MockProvider:
            name = "mock_ti"
            supported_types = ["ip"]

            async def lookup(self, indicator, ioc_type):
                nonlocal call_count
                call_count += 1
                return IOCResult(
                    indicator=indicator,
                    ioc_type="ip",
                    confidence=85,
                    provider="mock_ti",
                )

        svc.register_provider(MockProvider())

        # Event with only source_ip (no destination_ip) to get a single lookup
        event = {
            "event_type": "authentication",
            "severity": "medium",
            "source": "ssh-server",
            "description": "Failed login attempt",
            "source_ip": "1.2.3.4",
            "event_timestamp": "2025-01-15T10:30:00Z",
        }

        # First enrich — 1 lookup (source_ip only)
        await svc.enrich(event)
        assert call_count == 1

        # Second enrich uses cache — 0 new lookups
        await svc.enrich(event)
        assert call_count == 1  # Should not have called provider again
