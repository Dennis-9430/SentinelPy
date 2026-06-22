"""Tests de integración para los endpoints de la API.

Usa httpx con ASGITransport para testear FastAPI sin levantar el servidor.
Los tests corren sin base de datos — el lifespan maneja errores gracefulmente.
"""

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    """Fixture que provee la instancia de la aplicación FastAPI."""
    from app.main import app
    return app


@pytest.mark.asyncio
async def test_health_endpoint(app):
    """Verifica que el endpoint /health responda correctamente.

    Debería devolver status 200 con el estado 'healthy'.
    """
    # Crea un cliente HTTP asíncrono que habla directo con la app
    # Usamos el lifespan de la app que maneja errores gracefulmente
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["app"] == "SentinelPy"
