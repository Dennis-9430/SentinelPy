"""Tests for VirusTotal TI provider.

Covers: successful lookup (malicious > 0, clean), rate limit (429),
network error, IOCResult mapping, confidence calculation (malicious/total * 100),
all 3 supported types (ip, domain, hash).
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services.ti_providers.base import BaseTIProvider, IOCResult
from app.services.ti_providers.virustotal import VirusTotalProvider


def _make_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Crea un mock de httpx.Response con status_code y json()."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}

    def _raise_for_status():
        if 400 <= status_code < 600:
            raise httpx.HTTPStatusError(
                f"HTTP {status_code}",
                request=MagicMock(),
                response=resp,
            )

    resp.raise_for_status = _raise_for_status
    return resp


# ══════════════════════════════════════════════════════════════════════════
# Tests: VirusTotalProvider basics
# ══════════════════════════════════════════════════════════════════════════


class TestVirusTotalProviderBasics:
    """Verifica propiedades básicas del proveedor VirusTotal."""

    def test_name_returns_virustotal(self):
        """name property returns 'virustotal'."""
        provider = VirusTotalProvider(api_key="test_key")
        assert provider.name == "virustotal"

    def test_supported_types(self):
        """supported_types returns ip, domain, hash."""
        provider = VirusTotalProvider(api_key="test_key")
        assert provider.supported_types == ["ip", "domain", "hash"]

    def test_inherits_from_base(self):
        """VirusTotalProvider is a subclass of BaseTIProvider."""
        provider = VirusTotalProvider(api_key="test_key")
        assert isinstance(provider, BaseTIProvider)

    def test_api_key_header_set(self):
        """x-apikey header is set from api_key parameter."""
        provider = VirusTotalProvider(api_key="vt-key-123")
        assert provider._client.headers.get("x-apikey") == "vt-key-123"


# ══════════════════════════════════════════════════════════════════════════
# Tests: lookup_ip — success path
# ══════════════════════════════════════════════════════════════════════════


class TestVirusTotalLookupIPSuccess:
    """Verifica respuesta exitosa del API de VirusTotal para IPs."""

    async def test_success_malicious_maps_ioc_result(self):
        """Response with malicious engines maps confidence from ratio."""
        provider = VirusTotalProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={
                    "data": {
                        "attributes": {
                            "last_analysis_stats": {
                                "malicious": 15,
                                "total": 70,
                            },
                            "country": "US",
                        }
                    }
                },
            )
        )

        result = await provider.lookup_ip("1.2.3.4")

        assert result is not None
        assert isinstance(result, IOCResult)
        assert result.indicator == "1.2.3.4"
        assert result.ioc_type == "ip"
        assert result.confidence == 21  # 15/70 * 100 = 21.42 → int = 21
        assert result.provider == "virustotal"
        assert result.raw_response["country"] == "US"

    async def test_success_clean_returns_zero_confidence(self):
        """Response with 0 malicious engines returns confidence 0."""
        provider = VirusTotalProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={
                    "data": {
                        "attributes": {
                            "last_analysis_stats": {
                                "malicious": 0,
                                "total": 70,
                            }
                        }
                    }
                },
            )
        )

        result = await provider.lookup_ip("8.8.8.8")

        assert result is not None
        assert result.confidence == 0

    async def test_all_malicious_confidence_100(self):
        """When all engines flag malicious, confidence is 100."""
        provider = VirusTotalProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={
                    "data": {
                        "attributes": {
                            "last_analysis_stats": {
                                "malicious": 50,
                                "total": 50,
                            }
                        }
                    }
                },
            )
        )

        result = await provider.lookup_ip("10.0.0.1")

        assert result is not None
        assert result.confidence == 100


# ══════════════════════════════════════════════════════════════════════════
# Tests: lookup_domain — success path
# ══════════════════════════════════════════════════════════════════════════


class TestVirusTotalLookupDomainSuccess:
    """Verifica respuesta exitosa del API de VirusTotal para dominios."""

    async def test_domain_lookup_maps_ioc_result(self):
        """Domain lookup returns correct IOCResult with confidence ratio."""
        provider = VirusTotalProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={
                    "data": {
                        "attributes": {
                            "last_analysis_stats": {
                                "malicious": 10,
                                "total": 80,
                            }
                        }
                    }
                },
            )
        )

        result = await provider.lookup_domain("evil.com")

        assert result is not None
        assert result.indicator == "evil.com"
        assert result.ioc_type == "domain"
        assert result.confidence == 12  # 10/80 * 100 = 12.5 → int = 12
        assert result.provider == "virustotal"


# ══════════════════════════════════════════════════════════════════════════
# Tests: lookup_hash — success path
# ══════════════════════════════════════════════════════════════════════════


class TestVirusTotalLookupHashSuccess:
    """Verifica respuesta exitosa del API de VirusTotal para hashes."""

    async def test_hash_lookup_maps_ioc_result(self):
        """Hash lookup returns correct IOCResult with confidence ratio."""
        provider = VirusTotalProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={
                    "data": {
                        "attributes": {
                            "last_analysis_stats": {
                                "malicious": 40,
                                "total": 60,
                            }
                        }
                    }
                },
            )
        )

        result = await provider.lookup_hash("abc123def456")

        assert result is not None
        assert result.indicator == "abc123def456"
        assert result.ioc_type == "hash"
        assert result.confidence == 66  # 40/60 * 100 = 66.66 → int = 66
        assert result.provider == "virustotal"


# ══════════════════════════════════════════════════════════════════════════
# Tests: error paths
# ══════════════════════════════════════════════════════════════════════════


class TestVirusTotalLookupErrors:
    """Verifica manejo de errores del API de VirusTotal."""

    async def test_rate_limit_returns_none(self):
        """429 rate limit returns None silently."""
        provider = VirusTotalProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(status_code=429)
        )

        result = await provider.lookup_ip("1.2.3.4")
        assert result is None

    async def test_network_error_returns_none(self):
        """Network error (httpx.HTTPError) returns None."""
        provider = VirusTotalProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await provider.lookup_ip("1.2.3.4")
        assert result is None

    async def test_server_error_returns_none(self):
        """500 server error (raise_for_status) returns None."""
        provider = VirusTotalProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(status_code=500)
        )

        result = await provider.lookup_ip("1.2.3.4")
        assert result is None

    async def test_empty_response_returns_zero_confidence(self):
        """Response with empty data returns confidence 0."""
        provider = VirusTotalProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(status_code=200, json_data={"data": {}})
        )

        result = await provider.lookup_ip("1.2.3.4")

        assert result is not None
        assert result.confidence == 0

    async def test_missing_analysis_stats_returns_zero(self):
        """Response missing last_analysis_stats returns confidence 0."""
        provider = VirusTotalProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={"data": {"attributes": {}}},
            )
        )

        result = await provider.lookup_ip("1.2.3.4")

        assert result is not None
        assert result.confidence == 0


# ══════════════════════════════════════════════════════════════════════════
# Tests: URL construction
# ══════════════════════════════════════════════════════════════════════════


class TestVirusTotalURLConstruction:
    """Verifica que las URLs se construyen correctamente."""

    async def test_ip_url_path(self):
        """IP lookup uses /ip_addresses/{ip}."""
        provider = VirusTotalProvider(api_key="test_key")
        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={"data": {"attributes": {"last_analysis_stats": {"malicious": 0, "total": 1}}}},
            )
        )

        await provider.lookup_ip("8.8.8.8")

        call_args = provider._client.get.call_args[0][0]
        assert call_args == "https://www.virustotal.com/api/v3/ip_addresses/8.8.8.8"

    async def test_domain_url_path(self):
        """Domain lookup uses /domains/{domain}."""
        provider = VirusTotalProvider(api_key="test_key")
        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={"data": {"attributes": {"last_analysis_stats": {"malicious": 0, "total": 1}}}},
            )
        )

        await provider.lookup_domain("evil.com")

        call_args = provider._client.get.call_args[0][0]
        assert call_args == "https://www.virustotal.com/api/v3/domains/evil.com"

    async def test_hash_url_path(self):
        """Hash lookup uses /files/{hash}."""
        provider = VirusTotalProvider(api_key="test_key")
        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={"data": {"attributes": {"last_analysis_stats": {"malicious": 0, "total": 1}}}},
            )
        )

        await provider.lookup_hash("abc123")

        call_args = provider._client.get.call_args[0][0]
        assert call_args == "https://www.virustotal.com/api/v3/files/abc123"
