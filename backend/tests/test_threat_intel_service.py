"""Tests for ThreatIntelService.

Covers: cache hit/miss, TTL expiry, max cache eviction, provider failure,
enrich() collecting IPs, feeds property, disabled state.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.ti_providers.base import BaseTIProvider, IOCResult
from app.services.threat_intel_service import ThreatIntelService


# ══════════════════════════════════════════════════════════════════════════
# Fakes / Helpers
# ══════════════════════════════════════════════════════════════════════════


class _StubProvider(BaseTIProvider):
    """Proveedor stub que retorna un IOCResult configurable."""

    def __init__(
        self,
        provider_name: str = "stub",
        supported: list[str] | None = None,
        result: IOCResult | None = None,
    ) -> None:
        self._name = provider_name
        self._supported = supported or ["ip"]
        self._result = result
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_types(self) -> list[str]:
        return self._supported

    async def lookup_ip(self, indicator: str) -> IOCResult | None:
        self.call_count += 1
        return self._result


class _AlwaysFailProvider(BaseTIProvider):
    """Proveedor que siempre retorna None (simula fallo)."""

    @property
    def name(self) -> str:
        return "always_fail"

    @property
    def supported_types(self) -> list[str]:
        return ["ip"]

    async def lookup_ip(self, indicator: str) -> IOCResult | None:
        return None


def _make_result(indicator: str = "1.2.3.4", confidence: int = 85) -> IOCResult:
    return IOCResult(
        indicator=indicator,
        ioc_type="ip",
        confidence=confidence,
        provider="stub",
    )


# ══════════════════════════════════════════════════════════════════════════
# Tests: Cache behavior
# ══════════════════════════════════════════════════════════════════════════


class TestThreatIntelServiceCache:
    """Verifica cache hit, miss, y TTL expiry."""

    async def test_cache_hit_skips_provider(self):
        """Second lookup returns cached result without calling provider."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            provider = _StubProvider(result=_make_result())
            svc.register_provider(provider)

            # First call — cache miss, provider called
            result1 = await svc.lookup("1.2.3.4", "ip")
            assert result1 is not None
            assert provider.call_count == 1

            # Second call — cache hit, provider NOT called
            result2 = await svc.lookup("1.2.3.4", "ip")
            assert result2 is not None
            assert result2.indicator == "1.2.3.4"
            assert provider.call_count == 1  # still 1

    async def test_cache_miss_queries_provider(self):
        """Cache miss triggers provider lookup."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            provider = _StubProvider(result=_make_result())
            svc.register_provider(provider)

            result = await svc.lookup("1.2.3.4", "ip")
            assert result is not None
            assert provider.call_count == 1

    async def test_ttl_expiry_causes_requery(self):
        """Expired cache entry triggers a new provider query."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 0  # 0 minutes = immediate expiry

            svc = ThreatIntelService()
            provider = _StubProvider(result=_make_result())
            svc.register_provider(provider)

            # First call
            await svc.lookup("1.2.3.4", "ip")
            assert provider.call_count == 1

            # Second call — TTL is 0, so cache is expired
            await svc.lookup("1.2.3.4", "ip")
            assert provider.call_count == 2


# ══════════════════════════════════════════════════════════════════════════
# Tests: Cache eviction
# ══════════════════════════════════════════════════════════════════════════


class TestThreatIntelServiceCacheEviction:
    """Verifica que la cache evicts el más viejo al llegar al máximo."""

    async def test_max_cache_eviction(self):
        """Cache evicts oldest entry when exceeding max size (1000)."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            provider = _StubProvider(
                result=IOCResult(
                    indicator="x", ioc_type="ip", confidence=50, provider="stub"
                )
            )
            svc.register_provider(provider)

            # Fill cache to max (1000 entries) with unique indicators
            for i in range(1000):
                svc._cache[f"ip:10.0.0.{i % 256}.{i // 256}"] = (
                    _make_result(indicator=f"10.0.0.{i % 256}.{i // 256}"),
                    float(i),  # ascending timestamps
                )

            assert len(svc._cache) == 1000

            # Adding one more should evict the oldest
            result = await svc.lookup("new.indicator", "ip")
            assert result is not None
            # Cache should be at most 1000 (old one evicted, new one added)
            assert len(svc._cache) <= 1000


# ══════════════════════════════════════════════════════════════════════════
# Tests: Provider registration & failure
# ══════════════════════════════════════════════════════════════════════════


class TestThreatIntelServiceProviders:
    """Verifica registro de providers y manejo de fallos."""

    async def test_provider_failure_returns_none(self):
        """Provider returning None does not crash the service."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            svc.register_provider(_AlwaysFailProvider())

            result = await svc.lookup("1.2.3.4", "ip")
            assert result is None

    async def test_no_providers_returns_none(self):
        """lookup with no registered providers returns None."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            result = await svc.lookup("1.2.3.4", "ip")
            assert result is None


# ══════════════════════════════════════════════════════════════════════════
# Tests: Disabled state
# ══════════════════════════════════════════════════════════════════════════


class TestThreatIntelServiceDisabled:
    """Verifica comportamiento cuando TI está deshabilitado."""

    async def test_lookup_returns_none_when_disabled(self):
        """lookup returns None when ti_enrichment_enabled is False."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = False
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            svc.register_provider(_StubProvider(result=_make_result()))

            result = await svc.lookup("1.2.3.4", "ip")
            assert result is None

    async def test_enrich_returns_empty_when_disabled(self):
        """enrich() returns empty dict when ti_enrichment_enabled is False."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = False
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            result = await svc.enrich({"source_ip": "1.2.3.4"})
            assert result == {}


# ══════════════════════════════════════════════════════════════════════════
# Tests: enrich()
# ══════════════════════════════════════════════════════════════════════════


class TestThreatIntelServiceEnrich:
    """Verifica enriquecimiento de eventos con datos de TI."""

    async def test_enrich_collects_source_ip(self):
        """enrich() looks up source_ip from event dict."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            provider = _StubProvider(
                result=_make_result(indicator="1.2.3.4", confidence=90)
            )
            svc.register_provider(provider)

            result = await svc.enrich({"source_ip": "1.2.3.4"})

            assert "matches" in result
            assert len(result["matches"]) == 1
            assert result["matches"][0]["indicator"] == "1.2.3.4"
            assert result["matches"][0]["confidence"] == 90

    async def test_enrich_collects_destination_ip(self):
        """enrich() looks up destination_ip from event dict."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            provider = _StubProvider(
                result=_make_result(indicator="5.6.7.8", confidence=75)
            )
            svc.register_provider(provider)

            result = await svc.enrich({"destination_ip": "5.6.7.8"})

            assert "matches" in result
            assert len(result["matches"]) == 1
            assert result["matches"][0]["indicator"] == "5.6.7.8"

    async def test_enrich_collects_both_ips(self):
        """enrich() looks up both source_ip and destination_ip."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            # Provider returns different results per call
            call_results = [
                _make_result(indicator="1.2.3.4", confidence=80),
                _make_result(indicator="5.6.7.8", confidence=60),
            ]
            provider = _StubProvider(result=call_results[0])
            original_lookup = provider.lookup_ip
            call_idx = [0]

            async def mock_lookup(indicator):
                idx = min(call_idx[0], len(call_results) - 1)
                call_idx[0] += 1
                return call_results[idx]

            provider.lookup_ip = mock_lookup
            svc.register_provider(provider)

            result = await svc.enrich(
                {"source_ip": "1.2.3.4", "destination_ip": "5.6.7.8"}
            )

            assert "matches" in result
            assert len(result["matches"]) == 2

    async def test_enrich_returns_empty_when_no_matches(self):
        """enrich() returns empty dict when no IPs match."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            svc.register_provider(_AlwaysFailProvider())

            result = await svc.enrich({"source_ip": "1.2.3.4"})
            assert result == {}

    async def test_enrich_returns_empty_when_no_ips(self):
        """enrich() returns empty dict when event has no IP fields."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            result = await svc.enrich({"message": "hello"})
            assert result == {}


# ══════════════════════════════════════════════════════════════════════════
# Tests: feeds property
# ══════════════════════════════════════════════════════════════════════════


class TestThreatIntelServiceFeeds:
    """Verifica la propiedad feeds que lista providers registrados."""

    def test_feeds_returns_registered_providers(self):
        """feeds property returns list of registered provider info."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            svc.register_provider(_StubProvider(provider_name="alpha"))
            svc.register_provider(_StubProvider(provider_name="beta"))

            feeds = svc.feeds
            assert len(feeds) == 2
            names = [f["name"] for f in feeds]
            assert "alpha" in names
            assert "beta" in names

    def test_feeds_empty_when_no_providers(self):
        """feeds returns empty list when no providers registered."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            assert svc.feeds == []

    def test_feeds_contain_status_and_types(self):
        """Each feed entry has name, status, and supported_types."""
        with patch(
            "app.services.threat_intel_service.settings"
        ) as mock_settings:
            mock_settings.ti_enrichment_enabled = True
            mock_settings.ti_cache_ttl_minutes = 60

            svc = ThreatIntelService()
            svc.register_provider(
                _StubProvider(provider_name="gamma", supported=["ip", "domain"])
            )

            feed = svc.feeds[0]
            assert feed["name"] == "gamma"
            assert feed["status"] == "active"
            assert feed["supported_types"] == ["ip", "domain"]
