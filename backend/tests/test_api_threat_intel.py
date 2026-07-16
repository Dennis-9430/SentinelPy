"""Tests for api/threat_intel.py endpoints — TI API integration.

Covers: GET /feeds, POST /lookup (success + 404), GET /iocs (paginated)
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.ti_providers.base import IOCResult


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(session):
    from app.database import get_session
    from app.main import app

    async def override():
        yield session

    app.dependency_overrides[get_session] = override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
def mock_ti_service():
    """A ThreatIntelService with a mock provider for testing."""
    from app.services.threat_intel_service import ThreatIntelService

    svc = ThreatIntelService()

    class MockProvider:
        name = "mock_provider"
        supported_types = ["ip", "domain"]

        async def lookup(self, indicator, ioc_type):
            if indicator == "1.2.3.4":
                return IOCResult(
                    indicator="1.2.3.4",
                    ioc_type="ip",
                    confidence=85,
                    provider="mock_provider",
                )
            return None

    svc.register_provider(MockProvider())
    return svc


# ── Tests: GET /feeds ─────────────────────────────────────────────────────


class TestListFeeds:
    @pytest.mark.asyncio
    async def test_feeds_no_service(self, client):
        """When TI service is not available, return empty list."""
        from app.main import app

        # Ensure no ti_service on app.state
        old = getattr(app.state, "ti_service", None)
        app.state.ti_service = None
        try:
            resp = await client.get("/api/v1/threat-intel/feeds")
            assert resp.status_code == 200
            data = resp.json()
            assert data["feeds"] == []
        finally:
            app.state.ti_service = old

    @pytest.mark.asyncio
    async def test_feeds_with_providers(self, client, mock_ti_service):
        """When TI service has providers, return their status."""
        from app.main import app

        old = app.state.ti_service
        app.state.ti_service = mock_ti_service
        try:
            resp = await client.get("/api/v1/threat-intel/feeds")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["feeds"]) == 1
            feed = data["feeds"][0]
            assert feed["name"] == "mock_provider"
            assert feed["status"] == "active"
            assert "ip" in feed["supported_types"]
            assert "domain" in feed["supported_types"]
        finally:
            app.state.ti_service = old


# ── Tests: POST /lookup ───────────────────────────────────────────────────


class TestLookupIOC:
    @pytest.mark.asyncio
    async def test_lookup_no_service(self, client):
        """When TI service is not available, return 503."""
        from app.main import app

        old = getattr(app.state, "ti_service", None)
        app.state.ti_service = None
        try:
            resp = await client.post(
                "/api/v1/threat-intel/lookup",
                json={"indicator": "1.2.3.4", "ioc_type": "ip"},
            )
            assert resp.status_code == 503
            assert "not available" in resp.json()["detail"]
        finally:
            app.state.ti_service = old

    @pytest.mark.asyncio
    async def test_lookup_found(self, client, mock_ti_service):
        """When indicator is found, return IOCResultResponse."""
        from app.main import app

        old = app.state.ti_service
        app.state.ti_service = mock_ti_service
        try:
            resp = await client.post(
                "/api/v1/threat-intel/lookup",
                json={"indicator": "1.2.3.4", "ioc_type": "ip"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["indicator"] == "1.2.3.4"
            assert data["ioc_type"] == "ip"
            assert data["confidence"] == 85
            assert data["provider"] == "mock_provider"
        finally:
            app.state.ti_service = old

    @pytest.mark.asyncio
    async def test_lookup_not_found(self, client, mock_ti_service):
        """When indicator is unknown, return 404."""
        from app.main import app

        old = app.state.ti_service
        app.state.ti_service = mock_ti_service
        try:
            resp = await client.post(
                "/api/v1/threat-intel/lookup",
                json={"indicator": "99.99.99.99", "ioc_type": "ip"},
            )
            assert resp.status_code == 404
            assert "No results" in resp.json()["detail"]
        finally:
            app.state.ti_service = old

    @pytest.mark.asyncio
    async def test_lookup_invalid_type(self, client, mock_ti_service):
        """When ioc_type is invalid, return 422 (validation error)."""
        from app.main import app

        old = app.state.ti_service
        app.state.ti_service = mock_ti_service
        try:
            resp = await client.post(
                "/api/v1/threat-intel/lookup",
                json={"indicator": "1.2.3.4", "ioc_type": "invalid"},
            )
            assert resp.status_code == 422
        finally:
            app.state.ti_service = old

    @pytest.mark.asyncio
    async def test_lookup_empty_indicator(self, client, mock_ti_service):
        """When indicator is empty, return 422 (validation error)."""
        from app.main import app

        old = app.state.ti_service
        app.state.ti_service = mock_ti_service
        try:
            resp = await client.post(
                "/api/v1/threat-intel/lookup",
                json={"indicator": "", "ioc_type": "ip"},
            )
            assert resp.status_code == 422
        finally:
            app.state.ti_service = old


# ── Tests: GET /iocs ──────────────────────────────────────────────────────


class TestListIOCs:
    @pytest.mark.asyncio
    async def test_list_iocs_empty(self, client):
        """When no IOCs cached, return empty list with total=0."""
        resp = await client.get("/api/v1/threat-intel/iocs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["iocs"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_iocs_with_data(self, client, session):
        """When IOCs exist, return paginated list."""
        from datetime import UTC, datetime

        from app.models.threat_intel import IOCEntry

        # Seed IOC entries
        for i in range(3):
            ioc = IOCEntry(
                indicator=f"10.0.0.{i}",
                ioc_type="ip",
                provider="test_provider",
                confidence=50 + i,
                first_seen=datetime.now(UTC),
                last_seen=datetime.now(UTC),
            )
            session.add(ioc)
        await session.commit()

        resp = await client.get("/api/v1/threat-intel/iocs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["iocs"]) == 3
        # Check fields present
        ioc = data["iocs"][0]
        assert "id" in ioc
        assert "indicator" in ioc
        assert "ioc_type" in ioc
        assert "provider" in ioc
        assert "confidence" in ioc

    @pytest.mark.asyncio
    async def test_list_iocs_pagination(self, client, session):
        """When IOCs exceed limit, pagination works correctly."""
        from datetime import UTC, datetime

        from app.models.threat_intel import IOCEntry

        for i in range(5):
            ioc = IOCEntry(
                indicator=f"10.0.0.{i}",
                ioc_type="ip",
                provider="test_provider",
                confidence=50,
                first_seen=datetime.now(UTC),
                last_seen=datetime.now(UTC),
            )
            session.add(ioc)
        await session.commit()

        # Page 1
        resp = await client.get("/api/v1/threat-intel/iocs?limit=2&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["iocs"]) == 2

        # Page 2
        resp = await client.get("/api/v1/threat-intel/iocs?limit=2&offset=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["iocs"]) == 2

        # Page 3 (only 1 remaining)
        resp = await client.get("/api/v1/threat-intel/iocs?limit=2&offset=4")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["iocs"]) == 1
