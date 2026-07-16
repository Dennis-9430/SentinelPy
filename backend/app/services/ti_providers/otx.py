"""Proveedor de Threat Intelligence: AlienVault OTX.

Consulta la API pública de OTX DirectConnect para determinar
el nivel de amenaza asociado a IPs, dominios y hashes.
"""

import httpx

from app.services.ti_providers.base import BaseTIProvider, IOCResult


class OTXProvider(BaseTIProvider):
    """Proveedor de TI que consulta AlienVault OTX.

    Soporta IPs, dominios y hashes. La API pública no requiere
    clave para consultas básicas, pero se puede proveer una
    para mayor rate limit.

    Argumentos:
        api_key: Clave de API de OTX (opcional).
    """

    BASE_URL = "https://otx.alienvault.com/api/v1"

    def __init__(self, api_key: str = "") -> None:
        headers = {"Accept": "application/json"}
        if api_key:
            headers["X-OTX-API-KEY"] = api_key
        self._client = httpx.AsyncClient(headers=headers, timeout=10.0)

    @property
    def name(self) -> str:
        return "otx"

    @property
    def supported_types(self) -> list[str]:
        return ["ip", "domain", "hash"]

    async def lookup_ip(self, ip: str) -> IOCResult | None:
        """Consulta OTX para una dirección IP."""
        return await self._lookup(f"/indicators/IPv4/{ip}/general", ip, "ip")

    async def lookup_domain(self, domain: str) -> IOCResult | None:
        """Consulta OTX para un dominio."""
        return await self._lookup(f"/indicators/domain/{domain}/general", domain, "domain")

    async def lookup_hash(self, file_hash: str) -> IOCResult | None:
        """Consulta OTX para un hash de archivo."""
        return await self._lookup(f"/indicators/file/{file_hash}/general", file_hash, "hash")

    async def _lookup(
        self, path: str, indicator: str, ioc_type: str
    ) -> IOCResult | None:
        """Consulta genérica al API de OTX.

        Argumentos:
            path: Ruta del endpoint (ej: /indicators/IPv4/...).
            indicator: Valor del IOC consultado.
            ioc_type: Tipo del IOC.

        Retorna:
            IOCResult con confidence derivada del pulse count, o None si hay error.
        """
        try:
            resp = await self._client.get(f"{self.BASE_URL}{path}")
            if resp.status_code == 429:
                return None
            resp.raise_for_status()
            data = resp.json()
            pulse_count = data.get("pulse_info", {}).get("count", 0)
            # Convertir pulse count a confidence (0-100)
            confidence = min(pulse_count * 10, 100) if pulse_count > 0 else 0
            return IOCResult(
                indicator=indicator,
                ioc_type=ioc_type,
                confidence=confidence,
                provider="otx",
                raw_response=data,
            )
        except httpx.HTTPError:
            return None
