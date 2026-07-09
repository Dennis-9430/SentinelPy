"""Tests E2E para los endpoints de análisis.

Usa httpx con ASGITransport para testear FastAPI sin levantar servidor.
Los endpoints GET /api/analysis/anomalies y GET /api/analysis/risks
deberían responder 200 incluso sin datos de análisis.
"""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app():
    """Fixture que provee la instancia de la aplicación FastAPI."""
    from app.main import app

    return app


@pytest.mark.asyncio
async def test_get_anomalies_returns_200(app):
    """GET /api/analysis/anomalies devuelve 200 con lista vacía."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/analysis/anomalies")
        assert resp.status_code == 200
        data = resp.json()
        assert "anomalies" in data
        assert "total" in data
        assert isinstance(data["anomalies"], list)
        assert data["total"] >= 0


@pytest.mark.asyncio
async def test_get_anomalies_con_paginacion(app):
    """GET /api/analysis/anomalies acepta parámetros de paginación."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/analysis/anomalies?limit=10&offset=0")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_risks_returns_200(app):
    """GET /api/analysis/risks devuelve 200 con lista vacía."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/analysis/risks")
        assert resp.status_code == 200
        data = resp.json()
        assert "risks" in data
        assert "total" in data
        assert isinstance(data["risks"], list)
        assert data["total"] >= 0


@pytest.mark.asyncio
async def test_get_risks_con_paginacion(app):
    """GET /api/analysis/risks acepta parámetros de paginación."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/analysis/risks?limit=10&offset=0")
        assert resp.status_code == 200
