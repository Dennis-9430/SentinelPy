"""Tests for AbuseIPDB TI provider.

Covers: successful lookup, rate limit (429), network error,
IOCResult mapping, empty/missing data fields handled gracefully.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services.ti_providers.abuseipdb import AbuseIPDBProvider
from app.services.ti_providers.base import IOCResult


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
# Tests: AbuseIPDBProvider basics
# ══════════════════════════════════════════════════════════════════════════


class TestAbuseIPDBProviderBasics:
    """Verifica propiedades básicas del proveedor."""

    def test_name_returns_abuseipdb(self):
        """name property returns 'abuseipdb'."""
        provider = AbuseIPDBProvider(api_key="test_key")
        assert provider.name == "abuseipdb"

    def test_supported_types_is_ip_only(self):
        """supported_types returns only ['ip']."""
        provider = AbuseIPDBProvider(api_key="test_key")
        assert provider.supported_types == ["ip"]

    def test_inherits_from_base(self):
        """AbuseIPDBProvider is a subclass of BaseTIProvider."""
        from app.services.ti_providers.base import BaseTIProvider

        provider = AbuseIPDBProvider(api_key="test_key")
        assert isinstance(provider, BaseTIProvider)


# ══════════════════════════════════════════════════════════════════════════
# Tests: lookup_ip — success path
# ══════════════════════════════════════════════════════════════════════════


class TestAbuseIPDBLookupSuccess:
    """Verifica respuesta exitosa del API de AbuseIPDB."""

    async def test_success_maps_ioc_result(self):
        """Successful response maps to IOCResult with correct fields."""
        provider = AbuseIPDBProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={
                    "data": {
                        "ipAddress": "1.2.3.4",
                        "abuseConfidenceScore": 85,
                        "countryCode": "US",
                        "isp": "Test ISP",
                    }
                },
            )
        )

        result = await provider.lookup_ip("1.2.3.4")

        assert result is not None
        assert isinstance(result, IOCResult)
        assert result.indicator == "1.2.3.4"
        assert result.ioc_type == "ip"
        assert result.confidence == 85
        assert result.provider == "abuseipdb"
        assert result.raw_response["countryCode"] == "US"

    async def test_success_confidence_capped_at_100(self):
        """Confidence score > 100 is capped to 100."""
        provider = AbuseIPDBProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={"data": {"ipAddress": "10.0.0.1", "abuseConfidenceScore": 150}},
            )
        )

        result = await provider.lookup_ip("10.0.0.1")

        assert result is not None
        assert result.confidence == 100


# ══════════════════════════════════════════════════════════════════════════
# Tests: lookup_ip — error paths
# ══════════════════════════════════════════════════════════════════════════


class TestAbuseIPDBLookupErrors:
    """Verifica manejo de errores del API."""

    async def test_rate_limit_returns_none(self):
        """429 rate limit returns None silently."""
        provider = AbuseIPDBProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(status_code=429)
        )

        result = await provider.lookup_ip("1.2.3.4")
        assert result is None

    async def test_network_error_returns_none(self):
        """Network error (httpx.HTTPError) returns None."""
        provider = AbuseIPDBProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await provider.lookup_ip("1.2.3.4")
        assert result is None

    async def test_empty_data_returns_result_with_defaults(self):
        """Response with empty data dict returns result with confidence 0."""
        provider = AbuseIPDBProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(status_code=200, json_data={"data": {}})
        )

        result = await provider.lookup_ip("1.2.3.4")

        assert result is not None
        assert result.confidence == 0
        assert result.raw_response == {}

    async def test_missing_data_key_returns_result_with_defaults(self):
        """Response missing 'data' key returns result with confidence 0."""
        provider = AbuseIPDBProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(status_code=200, json_data={})
        )

        result = await provider.lookup_ip("1.2.3.4")

        assert result is not None
        assert result.confidence == 0
        assert result.raw_response == {}

    async def test_unsupported_type_returns_none(self):
        """Calling lookup with unsupported type returns None."""
        provider = AbuseIPDBProvider(api_key="test_key")
        result = await provider.lookup("evil.com", "domain")
        assert result is None

    async def test_server_error_returns_none(self):
        """500 server error (raise_for_status) returns None."""
        provider = AbuseIPDBProvider(api_key="test_key")

        provider._client.get = AsyncMock(
            return_value=_make_response(status_code=500)
        )

        result = await provider.lookup_ip("1.2.3.4")
        assert result is None
