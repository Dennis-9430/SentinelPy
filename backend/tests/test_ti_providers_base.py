"""Tests for BaseTIProvider ABC and IOCResult dataclass.

Covers: IOCResult creation, ABC instantiation guard, concrete dispatch,
unsupported type returns None, exception handling returns None.
"""

import pytest

from app.services.ti_providers.base import BaseTIProvider, IOCResult


# ══════════════════════════════════════════════════════════════════════════
# Tests: IOCResult
# ══════════════════════════════════════════════════════════════════════════


class TestIOCResult:
    """Verifica creación y campos del dataclass IOCResult."""

    def test_creation_with_required_fields(self):
        """IOCResult can be created with required fields only."""
        result = IOCResult(
            indicator="1.2.3.4",
            ioc_type="ip",
            confidence=85,
            provider="abuseipdb",
        )
        assert result.indicator == "1.2.3.4"
        assert result.ioc_type == "ip"
        assert result.confidence == 85
        assert result.provider == "abuseipdb"
        assert result.raw_response is None

    def test_creation_with_raw_response(self):
        """IOCResult accepts optional raw_response dict."""
        raw = {"abuseConfidenceScore": 85, "countryCode": "US"}
        result = IOCResult(
            indicator="evil.com",
            ioc_type="domain",
            confidence=70,
            provider="virustotal",
            raw_response=raw,
        )
        assert result.raw_response == raw
        assert result.raw_response["countryCode"] == "US"

    def test_ioc_types_include_all_variants(self):
        """IOCResult supports ip, domain, hash, url types."""
        for ioc_type in ("ip", "domain", "hash", "url"):
            result = IOCResult(
                indicator="test",
                ioc_type=ioc_type,
                confidence=50,
                provider="test",
            )
            assert result.ioc_type == ioc_type


# ══════════════════════════════════════════════════════════════════════════
# Tests: BaseTIProvider ABC
# ══════════════════════════════════════════════════════════════════════════


class TestBaseTIProviderABC:
    """Verifica que BaseTIProvider no puede instanciarse directamente."""

    def test_cannot_instantiate_directly(self):
        """BaseTIProvider is abstract — direct instantiation raises TypeError."""
        with pytest.raises(TypeError):
            BaseTIProvider()


# ══════════════════════════════════════════════════════════════════════════
# Tests: Concrete implementation dispatch
# ══════════════════════════════════════════════════════════════════════════


class _FakeProvider(BaseTIProvider):
    """Proveedor ficticio para tests — soporta tipo 'ip' y 'domain'."""

    @property
    def name(self) -> str:
        return "fake"

    @property
    def supported_types(self) -> list[str]:
        return ["ip", "domain"]

    async def lookup_ip(self, indicator: str) -> IOCResult:
        return IOCResult(
            indicator=indicator,
            ioc_type="ip",
            confidence=90,
            provider="fake",
        )

    async def lookup_domain(self, indicator: str) -> IOCResult:
        return IOCResult(
            indicator=indicator,
            ioc_type="domain",
            confidence=80,
            provider="fake",
        )


class _FailingProvider(BaseTIProvider):
    """Proveedor que lanza excepción en lookup_ip."""

    @property
    def name(self) -> str:
        return "failing"

    @property
    def supported_types(self) -> list[str]:
        return ["ip"]

    async def lookup_ip(self, indicator: str) -> IOCResult:
        raise ConnectionError("API caído")


class TestBaseTIProviderDispatch:
    """Verifica dispatch a métodos específicos por tipo."""

    async def test_dispatches_to_lookup_ip(self):
        """lookup('1.2.3.4', 'ip') llama a lookup_ip."""
        provider = _FakeProvider()
        result = await provider.lookup("1.2.3.4", "ip")
        assert result is not None
        assert result.ioc_type == "ip"
        assert result.indicator == "1.2.3.4"
        assert result.confidence == 90

    async def test_dispatches_to_lookup_domain(self):
        """lookup('evil.com', 'domain') llama a lookup_domain."""
        provider = _FakeProvider()
        result = await provider.lookup("evil.com", "domain")
        assert result is not None
        assert result.ioc_type == "domain"
        assert result.indicator == "evil.com"
        assert result.confidence == 80

    async def test_unsupported_type_returns_none(self):
        """lookup with unsupported type returns None."""
        provider = _FakeProvider()
        result = await provider.lookup("abc123", "hash")
        assert result is None

    async def test_exception_returns_none(self):
        """lookup catches exceptions and returns None."""
        provider = _FailingProvider()
        result = await provider.lookup("10.0.0.1", "ip")
        assert result is None
