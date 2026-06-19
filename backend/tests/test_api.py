"""Integration tests for the API."""

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    from app.main import app
    return app


@pytest.mark.asyncio
async def test_health_endpoint(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["app"] == "SentinelPy"
