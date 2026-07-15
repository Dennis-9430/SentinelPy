"""Tests for api/stats.py endpoints — lowest coverage at 40%.

Covers: GET /stats/events, GET /stats/alerts, GET /stats/alerts/exportar
"""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.alert_service import AlertService
from app.services.event_service import EventService
from app.services.rule_service import RuleService


def _evento_base() -> dict:
    return {
        "source": "stats-test-server",
        "collector_type": "test",
        "event_timestamp": datetime.now(UTC),
        "event_type": "test_event",
        "severity": "low",
        "description": "Evento para stats",
    }


def _regla_base() -> dict:
    return {
        "title": "Stats Test Rule",
        "description": "Rule for stats tests",
        "severity": "high",
        "status": "active",
        "conditions": {"operator": "AND", "conditions": []},
        "alert_title": "Stats Alert",
        "alert_severity": "high",
    }


def _alerta_base(rule_id) -> dict:
    return {
        "rule_id": rule_id,
        "title": "Alerta stats",
        "severity": "high",
        "description": "Alerta para test de stats",
        "status": "open",
        "event_count": 1,
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


class TestStatsEvents:
    @pytest.mark.asyncio
    async def test_stats_events_empty(self, client):
        response = await client.get("/api/stats/events")
        assert response.status_code == 200
        data = response.json()
        assert "timeline" in data
        assert "por_severidad" in data
        assert isinstance(data["timeline"], list)
        assert isinstance(data["por_severidad"], dict)

    @pytest.mark.asyncio
    async def test_stats_events_with_data(self, client, session):
        service = EventService(session)
        await service.crear_evento(_evento_base())
        datos2 = _evento_base()
        datos2["severity"] = "high"
        await service.crear_evento(datos2)

        response = await client.get("/api/stats/events?horas=24")
        assert response.status_code == 200
        data = response.json()
        assert len(data["timeline"]) >= 1
        assert "low" in data["por_severidad"]
        assert "high" in data["por_severidad"]

    @pytest.mark.asyncio
    async def test_stats_events_custom_hours(self, client):
        response = await client.get("/api/stats/events?horas=1")
        assert response.status_code == 200


class TestStatsAlerts:
    @pytest.mark.asyncio
    async def test_stats_alerts_empty(self, client):
        response = await client.get("/api/stats/alerts")
        assert response.status_code == 200
        data = response.json()
        assert "por_severidad" in data
        assert "por_estado" in data

    @pytest.mark.asyncio
    async def test_stats_alerts_with_data(self, client, session):
        rule_service = RuleService(session)
        regla = await rule_service.crear_regla(_regla_base())
        alert_service = AlertService(session)
        await alert_service.crear_alerta(_alerta_base(regla.id))
        a2 = _alerta_base(regla.id)
        a2["severity"] = "low"
        a2["status"] = "resolved"
        await alert_service.crear_alerta(a2)

        response = await client.get("/api/stats/alerts")
        assert response.status_code == 200
        data = response.json()
        assert data["por_severidad"].get("high", 0) >= 1
        assert data["por_estado"].get("open", 0) >= 1
        assert data["por_estado"].get("resolved", 0) >= 1


class TestExportarAlertasCsv:
    @pytest.mark.asyncio
    async def test_exportar_csv_empty(self, client):
        response = await client.get("/api/stats/alerts/exportar")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        content = response.text
        assert "id,titulo" in content

    @pytest.mark.asyncio
    async def test_exportar_csv_with_data(self, client, session):
        rule_service = RuleService(session)
        regla = await rule_service.crear_regla(_regla_base())
        alert_service = AlertService(session)
        await alert_service.crear_alerta(_alerta_base(regla.id))

        response = await client.get("/api/stats/alerts/exportar")
        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        assert len(lines) == 2  # header + 1 row

    @pytest.mark.asyncio
    async def test_exportar_csv_with_severity_filter(self, client, session):
        rule_service = RuleService(session)
        regla = await rule_service.crear_regla(_regla_base())
        alert_service = AlertService(session)
        await alert_service.crear_alerta(_alerta_base(regla.id))

        response = await client.get("/api/stats/alerts/exportar?severidad=high")
        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_exportar_csv_with_status_filter(self, client, session):
        rule_service = RuleService(session)
        regla = await rule_service.crear_regla(_regla_base())
        alert_service = AlertService(session)
        await alert_service.crear_alerta(_alerta_base(regla.id))

        response = await client.get("/api/stats/alerts/exportar?estado=open")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_exportar_csv_no_match_filter(self, client, session):
        rule_service = RuleService(session)
        regla = await rule_service.crear_regla(_regla_base())
        alert_service = AlertService(session)
        await alert_service.crear_alerta(_alerta_base(regla.id))

        response = await client.get("/api/stats/alerts/exportar?severidad=critical")
        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        assert len(lines) == 1  # header only
