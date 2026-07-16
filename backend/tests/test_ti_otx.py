"""Tests for OTX (AlienVault) TI provider.

Covers: successful lookup with pulses, no pulses, rate limit (429),
network error, IOCResult mapping, confidence from pulse count,
all 3 supported types (ip, domain, hash).
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services.ti_providers.base import BaseTIProvider, IOCResult
from app.services.ti_providers.otx import OTXProvider


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
# Tests: OTXProvider basics
# ══════════════════════════════════════════════════════════════════════════


class TestOTXProviderBasics:
    """Verifica propiedades básicas del proveedor OTX."""

    def test_name_returns_otx(self):
        """name property returns 'otx'."""
        provider = OTXProvider()
        assert provider.name == "otx"

    def test_supported_types(self):
        """supported_types returns ip, domain, hash."""
        provider = OTXProvider()
        assert provider.supported_types == ["ip", "domain", "hash"]

    def test_inherits_from_base(self):
        """OTXProvider is a subclass of BaseTIProvider."""
        provider = OTXProvider()
        assert isinstance(provider, BaseTIProvider)

    def test_optional_api_key_header(self):
        """When api_key is provided, X-OTX-API-KEY header is set."""
        provider = OTXProvider(api_key="test-key-123")
        assert provider._client.headers.get("X-OTX-API-KEY") == "test-key-123"

    def test_no_api_key_header_when_empty(self):
        """When api_key is empty, X-OTX-API-KEY header is not set."""
        provider = OTXProvider()
        assert "X-OTX-API-KEY" not in provider._client.headers


# ══════════════════════════════════════════════════════════════════════════
# Tests: lookup_ip — success path
# ══════════════════════════════════════════════════════════════════════════


class TestOTXLookupIPSuccess:
    """Verifica respuesta exitosa del API de OTX para IPs."""

    async def test_success_with_pulses_maps_ioc_result(self):
        """Response with pulse_count > 0 maps confidence from pulse count."""
        provider = OTXProvider()

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={
                    "pulse_info": {"count": 5},
                    "country_code": "US",
                },
            )
        )

        result = await provider.lookup_ip("1.2.3.4")

        assert result is not None
        assert isinstance(result, IOCResult)
        assert result.indicator == "1.2.3.4"
        assert result.ioc_type == "ip"
        assert result.confidence == 50  # 5 * 10
        assert result.provider == "otx"
        assert "pulse_info" in result.raw_response

    async def test_success_no_pulses_confidence_zero(self):
        """Response with pulse_count=0 returns confidence 0."""
        provider = OTXProvider()

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={"pulse_info": {"count": 0}},
            )
        )

        result = await provider.lookup_ip("1.2.3.4")

        assert result is not None
        assert result.confidence == 0

    async def test_success_many_pulses_capped_at_100(self):
        """Pulse count > 10 caps confidence at 100."""
        provider = OTXProvider()

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={"pulse_info": {"count": 15}},
            )
        )

        result = await provider.lookup_ip("10.0.0.1")

        assert result is not None
        assert result.confidence == 100  # 15 * 10 = 150, capped to 100


# ══════════════════════════════════════════════════════════════════════════
# Tests: lookup_domain — success path
# ══════════════════════════════════════════════════════════════════════════


class TestOTXLookupDomainSuccess:
    """Verifica respuesta exitosa del API de OTX para dominios."""

    async def test_domain_lookup_maps_ioc_result(self):
        """Domain lookup returns correct IOCResult with pulse confidence."""
        provider = OTXProvider()

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={"pulse_info": {"count": 8}},
            )
        )

        result = await provider.lookup_domain("evil.com")

        assert result is not None
        assert result.indicator == "evil.com"
        assert result.ioc_type == "domain"
        assert result.confidence == 80  # 8 * 10
        assert result.provider == "otx"


# ══════════════════════════════════════════════════════════════════════════
# Tests: lookup_hash — success path
# ══════════════════════════════════════════════════════════════════════════


class TestOTXLookupHashSuccess:
    """Verifica respuesta exitosa del API de OTX para hashes."""

    async def test_hash_lookup_maps_ioc_result(self):
        """Hash lookup returns correct IOCResult with pulse confidence."""
        provider = OTXProvider()

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={"pulse_info": {"count": 3}},
            )
        )

        result = await provider.lookup_hash("abc123def456")

        assert result is not None
        assert result.indicator == "abc123def456"
        assert result.ioc_type == "hash"
        assert result.confidence == 30  # 3 * 10
        assert result.provider == "otx"


# ══════════════════════════════════════════════════════════════════════════
# Tests: error paths
# ══════════════════════════════════════════════════════════════════════════


class TestOTXLookupErrors:
    """Verifica manejo de errores del API de OTX."""

    async def test_rate_limit_returns_none(self):
        """429 rate limit returns None silently."""
        provider = OTXProvider()

        provider._client.get = AsyncMock(
            return_value=_make_response(status_code=429)
        )

        result = await provider.lookup_ip("1.2.3.4")
        assert result is None

    async def test_network_error_returns_none(self):
        """Network error (httpx.HTTPError) returns None."""
        provider = OTXProvider()

        provider._client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await provider.lookup_ip("1.2.3.4")
        assert result is None

    async def test_server_error_returns_none(self):
        """500 server error (raise_for_status) returns None."""
        provider = OTXProvider()

        provider._client.get = AsyncMock(
            return_value=_make_response(status_code=500)
        )

        result = await provider.lookup_ip("1.2.3.4")
        assert result is None

    async def test_missing_pulse_info_returns_zero_confidence(self):
        """Response missing pulse_info returns confidence 0."""
        provider = OTXProvider()

        provider._client.get = AsyncMock(
            return_value=_make_response(
                status_code=200,
                json_data={"country_code": "US"},
            )
        )

        result = await provider.lookup_ip("1.2.3.4")

        assert result is not None
        assert result.confidence == 0


# ══════════════════════════════════════════════════════════════════════════
# Tests: URL construction
# ══════════════════════════════════════════════════════════════════════════


class TestOTXURLConstruction:
    """Verifica que las URLs se construyen correctamente."""

    async def test_ip_url_path(self):
        """IP lookup uses /indicators/IPv4/{ip}/general."""
        provider = OTXProvider()
        provider._client.get = AsyncMock(
            return_value=_make_response(status_code=200, json_data={"pulse_info": {"count": 0}})
        )

        await provider.lookup_ip("8.8.8.8")

        call_args = provider._client.get.call_args[0][0]
        assert call_args == "https://otx.alienvault.com/api/v1/indicators/IPv4/8.8.8.8/general"

    async def test_domain_url_path(self):
        """Domain lookup uses /indicators/domain/{domain}/general."""
        provider = OTXProvider()
        provider._client.get = AsyncMock(
            return_value=_make_response(status_code=200, json_data={"pulse_info": {"count": 0}})
        )

        await provider.lookup_domain("evil.com")

        call_args = provider._client.get.call_args[0][0]
        assert call_args == "https://otx.alienvault.com/api/v1/indicators/domain/evil.com/general"

    async def test_hash_url_path(self):
        """Hash lookup uses /indicators/file/{hash}/general."""
        provider = OTXProvider()
        provider._client.get = AsyncMock(
            return_value=_make_response(status_code=200, json_data={"pulse_info": {"count": 0}})
        )

        await provider.lookup_hash("abc123")

        call_args = provider._client.get.call_args[0][0]
        assert call_args == "https://otx.alienvault.com/api/v1/indicators/file/abc123/general"
