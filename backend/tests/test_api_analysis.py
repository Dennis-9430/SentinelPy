"""Tests for api/analysis.py endpoints — 54% coverage.

Covers: GET /analysis/anomalies, GET /analysis/risks
Tests both paths: analysis_service present and absent on app.state.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


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


class TestAnomalias:
    @pytest.mark.asyncio
    async def test_anomalias_sin_service(self, client):
        """When analysis_service is None, returns empty list."""
        from app.main import app

        saved = getattr(app.state, "analysis_service", None)
        app.state.analysis_service = None
        try:
            resp = await client.get("/api/analysis/anomalies")
            assert resp.status_code == 200
            data = resp.json()
            assert data["anomalies"] == []
            assert data["total"] == 0
        finally:
            app.state.analysis_service = saved

    @pytest.mark.asyncio
    async def test_anomalias_con_service_vacio(self, client):
        """When analysis_service exists but has no data."""
        from unittest.mock import AsyncMock, MagicMock

        from app.main import app

        mock_service = MagicMock()
        mock_service.get_anomalies = AsyncMock(return_value=([], 0))
        saved = getattr(app.state, "analysis_service", None)
        app.state.analysis_service = mock_service
        try:
            resp = await client.get("/api/analysis/anomalies")
            assert resp.status_code == 200
            data = resp.json()
            assert data["anomalies"] == []
            assert data["total"] == 0
        finally:
            app.state.analysis_service = saved

    @pytest.mark.asyncio
    async def test_anomalias_con_service_datos(self, client):
        """When analysis_service returns data."""
        from unittest.mock import AsyncMock, MagicMock

        from app.main import app

        mock_service = MagicMock()
        mock_service.get_anomalies = AsyncMock(
            return_value=([{"event_id": "1", "z_score": 3.0}], 1)
        )
        saved = getattr(app.state, "analysis_service", None)
        app.state.analysis_service = mock_service
        try:
            resp = await client.get("/api/analysis/anomalies?limite=10&desde=0")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert len(data["anomalies"]) == 1
        finally:
            app.state.analysis_service = saved

    @pytest.mark.asyncio
    async def test_anomalias_service_error(self, client):
        """When analysis_service raises an exception, returns empty."""
        from unittest.mock import AsyncMock, MagicMock

        from app.main import app

        mock_service = MagicMock()
        mock_service.get_anomalies = AsyncMock(side_effect=Exception("DB error"))
        saved = getattr(app.state, "analysis_service", None)
        app.state.analysis_service = mock_service
        try:
            resp = await client.get("/api/analysis/anomalies")
            assert resp.status_code == 200
            data = resp.json()
            assert data["anomalies"] == []
            assert data["total"] == 0
        finally:
            app.state.analysis_service = saved


class TestRisks:
    @pytest.mark.asyncio
    async def test_risks_sin_service(self, client):
        from app.main import app

        saved = getattr(app.state, "analysis_service", None)
        app.state.analysis_service = None
        try:
            resp = await client.get("/api/analysis/risks")
            assert resp.status_code == 200
            data = resp.json()
            assert data["risks"] == []
            assert data["total"] == 0
        finally:
            app.state.analysis_service = saved

    @pytest.mark.asyncio
    async def test_risks_con_service_vacio(self, client):
        from unittest.mock import AsyncMock, MagicMock

        from app.main import app

        mock_service = MagicMock()
        mock_service.get_risks = AsyncMock(return_value=([], 0))
        saved = getattr(app.state, "analysis_service", None)
        app.state.analysis_service = mock_service
        try:
            resp = await client.get("/api/analysis/risks")
            assert resp.status_code == 200
            assert resp.json()["risks"] == []
        finally:
            app.state.analysis_service = saved

    @pytest.mark.asyncio
    async def test_risks_con_service_datos(self, client):
        from unittest.mock import AsyncMock, MagicMock

        from app.main import app

        mock_service = MagicMock()
        mock_service.get_risks = AsyncMock(
            return_value=([{"entity_key": "10.0.0.1", "risk_score": 0.8}], 1)
        )
        saved = getattr(app.state, "analysis_service", None)
        app.state.analysis_service = mock_service
        try:
            resp = await client.get("/api/analysis/risks")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
        finally:
            app.state.analysis_service = saved

    @pytest.mark.asyncio
    async def test_risks_service_error(self, client):
        from unittest.mock import AsyncMock, MagicMock

        from app.main import app

        mock_service = MagicMock()
        mock_service.get_risks = AsyncMock(side_effect=Exception("DB error"))
        saved = getattr(app.state, "analysis_service", None)
        app.state.analysis_service = mock_service
        try:
            resp = await client.get("/api/analysis/risks")
            assert resp.status_code == 200
            data = resp.json()
            assert data["risks"] == []
            assert data["total"] == 0
        finally:
            app.state.analysis_service = saved
