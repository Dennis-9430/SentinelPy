"""Proveedor de Threat Intelligence: VirusTotal.

Consulta la API v3 de VirusTotal para determinar el nivel de amenaza
asociado a IPs, dominios y hashes, basado en el ratio de motores
que lo reportan como malicioso.
"""

import httpx

from app.services.ti_providers.base import BaseTIProvider, IOCResult


class VirusTotalProvider(BaseTIProvider):
    """Proveedor de TI que consulta VirusTotal API v3.

    Requiere una API key (free tier: 4 requests/min).
    Calcula confidence como (malicious / total) * 100.

    Argumentos:
        api_key: Clave de API de VirusTotal (requerida).
    """

    BASE_URL = "https://www.virustotal.com/api/v3"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            headers={"x-apikey": api_key, "Accept": "application/json"},
            timeout=10.0,
        )

    @property
    def name(self) -> str:
        return "virustotal"

    @property
    def supported_types(self) -> list[str]:
        return ["ip", "domain", "hash"]

    async def lookup_ip(self, ip: str) -> IOCResult | None:
        """Consulta VirusTotal para una dirección IP."""
        return await self._lookup(f"/ip_addresses/{ip}", ip, "ip")

    async def lookup_domain(self, domain: str) -> IOCResult | None:
        """Consulta VirusTotal para un dominio."""
        return await self._lookup(f"/domains/{domain}", domain, "domain")

    async def lookup_hash(self, file_hash: str) -> IOCResult | None:
        """Consulta VirusTotal para un hash de archivo."""
        return await self._lookup(f"/files/{file_hash}", file_hash, "hash")

    async def _lookup(
        self, path: str, indicator: str, ioc_type: str
    ) -> IOCResult | None:
        """Consulta genérica al API de VirusTotal.

        Calcula confidence como (malicious / total) * 100.

        Argumentos:
            path: Ruta del endpoint (ej: /ip_addresses/...).
            indicator: Valor del IOC consultado.
            ioc_type: Tipo del IOC.

        Retorna:
            IOCResult con confidence del ratio malicious/total, o None si hay error.
        """
        try:
            resp = await self._client.get(f"{self.BASE_URL}{path}")
            if resp.status_code == 429:
                return None
            resp.raise_for_status()
            data = resp.json().get("data", {}).get("attributes", {})
            stats = data.get("last_analysis_stats", {})
            malicious = stats.get("malicious", 0)
            total = max(stats.get("total", 1), 1)
            confidence = min(int((malicious / total) * 100), 100)
            return IOCResult(
                indicator=indicator,
                ioc_type=ioc_type,
                confidence=confidence,
                provider="virustotal",
                raw_response=data,
            )
        except httpx.HTTPError:
            return None
