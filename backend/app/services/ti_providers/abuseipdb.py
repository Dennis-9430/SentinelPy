"""Proveedor de Threat Intelligence: AbuseIPDB.

Consulta la API de AbuseIPDB para determinar el nivel de abuso
asociado a una dirección IP.
"""

import httpx

from app.services.ti_providers.base import BaseTIProvider, IOCResult


class AbuseIPDBProvider(BaseTIProvider):
    """Proveedor de TI que consulta AbuseIPDB para IPs.

    Argumentos:
        api_key: Clave de API de AbuseIPDB.
    """

    BASE_URL = "https://api.abuseipdb.com/api/v2"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            headers={"Key": api_key, "Accept": "application/json"},
            timeout=10.0,
        )

    @property
    def name(self) -> str:
        return "abuseipdb"

    @property
    def supported_types(self) -> list[str]:
        return ["ip"]

    async def lookup_ip(self, ip: str) -> IOCResult | None:
        """Consulta AbuseIPDB para una dirección IP.

        Argumentos:
            ip: Dirección IP a consultar.

        Retorna:
            IOCResult con el score de abuso, o None si hay error/rate limit.
        """
        try:
            resp = await self._client.get(
                f"{self.BASE_URL}/check",
                params={"ipAddress": ip, "maxAgeInDays": 90},
            )
            if resp.status_code == 429:
                return None
            resp.raise_for_status()
            data = resp.json().get("data", {})
            score = data.get("abuseConfidenceScore", 0)
            return IOCResult(
                indicator=ip,
                ioc_type="ip",
                confidence=min(score, 100),
                provider="abuseipdb",
                raw_response=data,
            )
        except httpx.HTTPError:
            return None
