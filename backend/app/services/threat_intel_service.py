"""Threat Intelligence service: provider orchestration, cache, enrichment.

Registers TI providers, keeps a TTL cache,
and enriches events with data from queried IOCs.
"""

import time
from typing import Any

from app.config import settings
from app.services.ti_providers.base import BaseTIProvider, IOCResult


class ThreatIntelService:
    """Service that orchestrates queries to TI providers.

    Handles provider registration, TTL cache, and enrichment
    of events with Indicators of Compromise (IOCs) data.
    """

    def __init__(self) -> None:
        self._providers: dict[str, BaseTIProvider] = {}
        self._cache: dict[str, tuple[IOCResult, float]] = {}
        self._cache_ttl = settings.ti_cache_ttl_minutes * 60  # convert to seconds
        self._max_cache_size = 1000
        self._enabled = settings.ti_enrichment_enabled

    def register_provider(self, provider: BaseTIProvider) -> None:
        """Registers a TI provider.

        Args:
            provider: Instance of a concrete BaseTIProvider.
        """
        self._providers[provider.name] = provider

    def _get_cache_key(self, indicator: str, ioc_type: str) -> str:
        """Generates the cache key for an IOC."""
        return f"{ioc_type}:{indicator}"

    def _get_cached(self, indicator: str, ioc_type: str) -> IOCResult | None:
        """Gets a cached result if it exists and has not expired."""
        key = self._get_cache_key(indicator, ioc_type)
        if key in self._cache:
            result, ts = self._cache[key]
            if time.time() - ts < self._cache_ttl:
                return result
            del self._cache[key]
        return None

    def _set_cache(self, indicator: str, ioc_type: str, result: IOCResult) -> None:
        """Stores a result in the cache, evicting the oldest if full."""
        if len(self._cache) >= self._max_cache_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        key = self._get_cache_key(indicator, ioc_type)
        self._cache[key] = (result, time.time())

    async def lookup(self, indicator: str, ioc_type: str) -> IOCResult | None:
        """Looks up an IOC through the registered providers.

        Checks the cache first. If there is no hit, queries each provider
        that supports the requested type.

        Args:
            indicator: Value of the IOC to look up.
            ioc_type: IOC type (ip, domain, hash, url).

        Returns:
            IOCResult from the first provider that returns a result, or None.
        """
        if not self._enabled:
            return None

        cached = self._get_cached(indicator, ioc_type)
        if cached:
            return cached

        for provider in self._providers.values():
            if ioc_type in provider.supported_types:
                result = await provider.lookup(indicator, ioc_type)
                if result:
                    self._set_cache(indicator, ioc_type, result)
                    return result

        return None

    async def enrich(self, event_dict: dict[str, Any]) -> dict[str, Any]:
        """Enriches an event with Threat Intelligence data.

        Extracts source_ip and destination_ip from the event, looks them
        up through lookup(), and returns the matches found.

        Args:
            event_dict: Dict of the event to enrich.

        Returns:
            Dict with the 'matches' key (list of found IOCs),
            or an empty dict if there are no matches or TI is disabled.
        """
        if not self._enabled:
            return {}

        matches = []
        ips_to_check: set[tuple[str, str]] = set()

        if event_dict.get("source_ip"):
            ips_to_check.add(("ip", event_dict["source_ip"]))
        if event_dict.get("destination_ip"):
            ips_to_check.add(("ip", event_dict["destination_ip"]))

        for ioc_type, indicator in ips_to_check:
            result = await self.lookup(indicator, ioc_type)
            if result:
                matches.append({
                    "type": result.ioc_type,
                    "indicator": result.indicator,
                    "confidence": result.confidence,
                    "provider": result.provider,
                })

        return {"matches": matches} if matches else {}

    @property
    def feeds(self) -> list[dict[str, Any]]:
        """Returns the status of all registered providers."""
        return [
            {
                "name": provider.name,
                "status": "active",
                "supported_types": provider.supported_types,
            }
            for provider in self._providers.values()
        ]
