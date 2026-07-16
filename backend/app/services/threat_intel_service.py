"""Servicio de Threat Intelligence: orquestación de providers, cache, enriquecimiento.

Registra providers de TI, mantiene un cache con TTL,
y enriquece eventos con datos de IOCs consultados.
"""

import time
from typing import Any

from app.config import settings
from app.services.ti_providers.base import BaseTIProvider, IOCResult


class ThreatIntelService:
    """Servicio que orquesta consultas a proveedores de TI.

    Maneja registro de providers, cache con TTL, y enriquecimiento
    de eventos con datos de Indicadores de Compromiso (IOCs).
    """

    def __init__(self) -> None:
        self._providers: dict[str, BaseTIProvider] = {}
        self._cache: dict[str, tuple[IOCResult, float]] = {}
        self._cache_ttl = settings.ti_cache_ttl_minutes * 60  # convertir a segundos
        self._max_cache_size = 1000
        self._enabled = settings.ti_enrichment_enabled

    def register_provider(self, provider: BaseTIProvider) -> None:
        """Registra un proveedor de TI.

        Argumentos:
            provider: Instancia de un BaseTIProvider concreto.
        """
        self._providers[provider.name] = provider

    def _get_cache_key(self, indicator: str, ioc_type: str) -> str:
        """Genera la clave de cache para un IOC."""
        return f"{ioc_type}:{indicator}"

    def _get_cached(self, indicator: str, ioc_type: str) -> IOCResult | None:
        """Obtiene un resultado de cache si existe y no expiró."""
        key = self._get_cache_key(indicator, ioc_type)
        if key in self._cache:
            result, ts = self._cache[key]
            if time.time() - ts < self._cache_ttl:
                return result
            del self._cache[key]
        return None

    def _set_cache(self, indicator: str, ioc_type: str, result: IOCResult) -> None:
        """Almacena un resultado en cache, evicting el más viejo si está lleno."""
        if len(self._cache) >= self._max_cache_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        key = self._get_cache_key(indicator, ioc_type)
        self._cache[key] = (result, time.time())

    async def lookup(self, indicator: str, ioc_type: str) -> IOCResult | None:
        """Consulta un IOC a través de los providers registrados.

        Verifica cache primero. Si no hay hit, consulta cada provider
        que soporte el tipo indicado.

        Argumentos:
            indicator: Valor del IOC a consultar.
            ioc_type: Tipo del IOC (ip, domain, hash, url).

        Retorna:
            IOCResult del primer provider que retorne resultado, o None.
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
        """Enriquece un evento con datos de Threat Intelligence.

        Extrae source_ip y destination_ip del evento, los consulta
        a través de lookup(), y retorna las coincidencias encontradas.

        Argumentos:
            event_dict: Dict del evento a enriquecer.

        Retorna:
            Dict con clave 'matches' (lista de IOCs encontrados),
            o dict vacío si no hay coincidencias o TI está deshabilitado.
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
        """Retorna el estado de todos los providers registrados."""
        return [
            {
                "name": provider.name,
                "status": "active",
                "supported_types": provider.supported_types,
            }
            for provider in self._providers.values()
        ]
