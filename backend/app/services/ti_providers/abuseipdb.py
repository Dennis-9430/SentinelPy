"""Threat Intelligence provider: AbuseIPDB.

Queries the AbuseIPDB API to determine the abuse level
associated with an IP address.
"""

import httpx

from app.services.ti_providers.base import BaseTIProvider, IOCResult


class AbuseIPDBProvider(BaseTIProvider):
    """TI provider that queries AbuseIPDB for IPs.

    Args:
        api_key: AbuseIPDB API key.
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
        """Queries AbuseIPDB for an IP address.

        Args:
            ip: IP address to look up.

        Returns:
            IOCResult with the abuse score, or None on error/rate limit.
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
