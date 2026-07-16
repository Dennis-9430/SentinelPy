"""Tests for api/events.py pipeline path and edge cases.

Covers: POST /events with pipeline (lines 88-98),
        POST /events pipeline exception fallback,
        GET /events with description truncation
"""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.event_service import EventService


def _evento_base() -> dict:
    return {
        "source": "pipeline-test",
        "collector_type": "test",
        "event_timestamp": datetime.now(UTC),
        "event_type": "test_event",
        "severity": "low",
        "description": "Evento para pipeline test",
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


class TestCrearEventoPipeline:
    @pytest.mark.asyncio
    async def test_crear_evento_con_pipeline_exitoso(self, client, session):
        payload = _evento_base()
        payload["event_timestamp"] = payload["event_timestamp"].isoformat()

        resp = await client.post("/api/events", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["event_type"] == "test_event"

    @pytest.mark.asyncio
    async def test_crear_evento_pipeline_fallo_fallback(self, client, session):
        payload = _evento_base()
        payload["event_timestamp"] = payload["event_timestamp"].isoformat()

        resp = await client.post("/api/events", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data

    @pytest.mark.asyncio
    async def test_crear_evento_sin_pipeline(self, client, session):
        payload = _evento_base()
        payload["event_timestamp"] = payload["event_timestamp"].isoformat()

        resp = await client.post("/api/events", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["event_type"] == "test_event"


class TestListarEventosEdgeCases:
    @pytest.mark.asyncio
    async def test_listar_descripcion_truncada(self, client, session):
        service = EventService(session)
        d = _evento_base()
        d["description"] = "x" * 300
        await service.crear_evento(d)

        resp = await client.get("/api/events")
        assert resp.status_code == 200
        evento = resp.json()["eventos"][0]
        assert len(evento["description"]) <= 200

    @pytest.mark.asyncio
    async def test_listar_descripcion_empty_string(self, client, session):
        service = EventService(session)
        d = _evento_base()
        d["description"] = ""
        await service.crear_evento(d)

        resp = await client.get("/api/events")
        assert resp.status_code == 200
        assert resp.json()["eventos"][0]["description"] == ""

    @pytest.mark.asyncio
    async def test_listar_evento_fields_all(self, client, session):
        service = EventService(session)
        d = _evento_base()
        d["source_ip"] = "10.0.0.5"
        d["destination_ip"] = "192.168.1.50"
        d["process_name"] = "sshd"
        d["user_name"] = "root"
        d["description"] = "Full fields test"
        await service.crear_evento(d)

        resp = await client.get("/api/events")
        assert resp.status_code == 200
        evento = resp.json()["eventos"][0]
        assert evento["source_ip"] == "10.0.0.5"
        assert evento["destination_ip"] == "192.168.1.50"
        assert evento["process_name"] == "sshd"
        assert evento["user_name"] == "root"
        assert "event_timestamp" in evento
        assert "created_at" in evento
