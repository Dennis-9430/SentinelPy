"""Tests for api/events.py endpoints — 44% coverage.

Covers: GET /events, POST /events, GET /events/estadisticas
"""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.event_service import EventService


def _evento_base() -> dict:
    return {
        "source": "api-events-test",
        "collector_type": "test",
        "event_timestamp": datetime.now(UTC),
        "event_type": "test_event",
        "severity": "low",
        "description": "Evento para events API",
    }


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


class TestListarEventos:
    @pytest.mark.asyncio
    async def test_listar_vacio(self, client):
        response = await client.get("/api/events")
        assert response.status_code == 200
        data = response.json()
        assert data["eventos"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_listar_con_datos(self, client, session):
        service = EventService(session)
        for i in range(3):
            d = _evento_base()
            d["description"] = f"Evento {i}"
            await service.crear_evento(d)

        response = await client.get("/api/events?limite=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["eventos"]) == 3

    @pytest.mark.asyncio
    async def test_listar_paginacion(self, client, session):
        service = EventService(session)
        for i in range(5):
            d = _evento_base()
            d["description"] = f"Evento {i}"
            await service.crear_evento(d)

        resp1 = await client.get("/api/events?limite=2&desde=0")
        resp2 = await client.get("/api/events?limite=2&desde=2")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert len(resp1.json()["eventos"]) == 2
        assert resp1.json()["eventos"][0]["id"] != resp2.json()["eventos"][0]["id"]

    @pytest.mark.asyncio
    async def test_listar_filtro_tipo(self, client, session):
        service = EventService(session)
        d1 = _evento_base()
        d1["event_type"] = "auth_failure"
        await service.crear_evento(d1)
        d2 = _evento_base()
        d2["event_type"] = "port_scan"
        await service.crear_evento(d2)

        resp = await client.get("/api/events?tipo=auth_failure")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["eventos"][0]["event_type"] == "auth_failure"

    @pytest.mark.asyncio
    async def test_listar_filtro_severidad(self, client, session):
        service = EventService(session)
        d1 = _evento_base()
        d1["severity"] = "high"
        await service.crear_evento(d1)
        d2 = _evento_base()
        d2["severity"] = "low"
        await service.crear_evento(d2)

        resp = await client.get("/api/events?severidad=high")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["eventos"][0]["severity"] == "high"

    @pytest.mark.asyncio
    async def test_listar_evento_fields(self, client, session):
        service = EventService(session)
        d = _evento_base()
        d["source_ip"] = "10.0.0.1"
        d["destination_ip"] = "192.168.1.100"
        d["process_name"] = "sshd"
        d["user_name"] = "root"
        await service.crear_evento(d)

        resp = await client.get("/api/events")
        evento = resp.json()["eventos"][0]
        assert "id" in evento
        assert "source" in evento
        assert "event_timestamp" in evento
        assert "created_at" in evento
        assert evento["source_ip"] == "10.0.0.1"
        assert evento["user_name"] == "root"


class TestCrearEvento:
    @pytest.mark.asyncio
    async def test_crear_evento_directo(self, client, session):
        """POST /events without pipeline (pipeline may not be set in test)."""
        payload = _evento_base()
        payload["event_timestamp"] = payload["event_timestamp"].isoformat()

        response = await client.post("/api/events", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["event_type"] == "test_event"

    @pytest.mark.asyncio
    async def test_crear_evento_respuesta_campos(self, client, session):
        payload = _evento_base()
        payload["event_timestamp"] = payload["event_timestamp"].isoformat()

        response = await client.post("/api/events", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert "event_type" in data
        assert "severity" in data
        assert "source" in data
        assert "event_timestamp" in data
        assert "created_at" in data


class TestEstadisticas:
    @pytest.mark.asyncio
    async def test_estadisticas_sin_datos(self, client):
        resp = await client.get("/api/events/estadisticas")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_eventos"] == 0

    @pytest.mark.asyncio
    async def test_estadisticas_con_datos(self, client, session):
        service = EventService(session)
        await service.crear_evento(_evento_base())
        await service.crear_evento(_evento_base())

        resp = await client.get("/api/events/estadisticas")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_eventos"] == 2
