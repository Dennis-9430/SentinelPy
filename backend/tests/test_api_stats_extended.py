"""Tests for api/stats.py — covering CSV export with resolved_at and data paths.

Covers: GET /stats/events with data, GET /stats/alerts with data,
        GET /stats/alerts/exportar with resolved alerts
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
        "source": "stats-ext-test",
        "collector_type": "test",
        "event_timestamp": datetime.now(UTC),
        "event_type": "test_event",
        "severity": "low",
        "description": "Evento para stats extendido",
    }


def _regla_base() -> dict:
    return {
        "title": "Stats Ext Rule",
        "description": "Rule for stats extended tests",
        "severity": "high",
        "status": "active",
        "conditions": {"operator": "AND", "conditions": []},
        "alert_title": "Stats Ext Alert",
        "alert_severity": "high",
    }


def _alerta_base(rule_id) -> dict:
    return {
        "rule_id": rule_id,
        "title": "Alerta stats ext",
        "severity": "high",
        "description": "Alerta para test de stats extendido",
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


class TestStatsEventsExtended:
    @pytest.mark.asyncio
    async def test_timeline_with_multiple_events(self, client, session):
        service = EventService(session)
        for i in range(3):
            d = _evento_base()
            d["event_type"] = f"event_{i}"
            await service.crear_evento(d)

        resp = await client.get("/api/stats/events?horas=24")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["timeline"]) >= 1
        assert data["timeline"][0]["total"] >= 3

    @pytest.mark.asyncio
    async def test_por_severidad_multiple_levels(self, client, session):
        service = EventService(session)
        for sev in ["low", "medium", "high", "critical"]:
            d = _evento_base()
            d["severity"] = sev
            await service.crear_evento(d)

        resp = await client.get("/api/stats/events?horas=24")
        assert resp.status_code == 200
        data = resp.json()
        for sev in ["low", "medium", "high", "critical"]:
            assert sev in data["por_severidad"]
            assert data["por_severidad"][sev] >= 1

    @pytest.mark.asyncio
    async def test_por_severidad_unknown(self, client, session):
        service = EventService(session)
        d = _evento_base()
        d["severity"] = None
        await service.crear_evento(d)

        resp = await client.get("/api/stats/events?horas=24")
        assert resp.status_code == 200
        data = resp.json()
        assert "unknown" in data["por_severidad"]


class TestStatsAlertsExtended:
    @pytest.mark.asyncio
    async def test_por_severidad_and_estado(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)

        a1 = _alerta_base(regla.id)
        a1["severity"] = "critical"
        a1["status"] = "open"
        await alert_svc.crear_alerta(a1)

        a2 = _alerta_base(regla.id)
        a2["severity"] = "low"
        a2["status"] = "resolved"
        await alert_svc.crear_alerta(a2)

        a3 = _alerta_base(regla.id)
        a3["severity"] = "medium"
        a3["status"] = "investigating"
        await alert_svc.crear_alerta(a3)

        resp = await client.get("/api/stats/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["por_severidad"]["critical"] >= 1
        assert data["por_severidad"]["low"] >= 1
        assert data["por_severidad"]["medium"] >= 1
        assert data["por_estado"]["open"] >= 1
        assert data["por_estado"]["resolved"] >= 1
        assert data["por_estado"]["investigating"] >= 1

    @pytest.mark.asyncio
    async def test_por_severidad_unknown_severity(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)

        a = _alerta_base(regla.id)
        a["severity"] = None
        await alert_svc.crear_alerta(a)

        resp = await client.get("/api/stats/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "unknown" in data["por_severidad"]


class TestExportarCsvExtended:
    @pytest.mark.asyncio
    async def test_csv_with_resolved_at(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        alerta = await alert_svc.crear_alerta(_alerta_base(regla.id))
        await alert_svc.actualizar_estado(str(alerta.id), "resolved")

        resp = await client.get("/api/stats/alerts/exportar")
        assert resp.status_code == 200
        content = resp.text
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert "resolved" in lines[1]

    @pytest.mark.asyncio
    async def test_csv_with_description(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        alerta_data = _alerta_base(regla.id)
        alerta_data["description"] = "Test description for CSV export"
        await alert_svc.crear_alerta(alerta_data)

        resp = await client.get("/api/stats/alerts/exportar")
        assert resp.status_code == 200
        assert "Test description for CSV export" in resp.text

    @pytest.mark.asyncio
    async def test_csv_with_no_description(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        alerta_data = _alerta_base(regla.id)
        alerta_data["description"] = None
        await alert_svc.crear_alerta(alerta_data)

        resp = await client.get("/api/stats/alerts/exportar")
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_csv_multiple_rows(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        for i in range(3):
            d = _alerta_base(regla.id)
            d["title"] = f"Alerta CSV {i}"
            await alert_svc.crear_alerta(d)

        resp = await client.get("/api/stats/alerts/exportar")
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) == 4  # header + 3 rows

    @pytest.mark.asyncio
    async def test_csv_with_state_filter(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)

        a1 = _alerta_base(regla.id)
        a1["status"] = "open"
        await alert_svc.crear_alerta(a1)

        a2 = _alerta_base(regla.id)
        a2["status"] = "resolved"
        await alert_svc.crear_alerta(a2)

        resp = await client.get("/api/stats/alerts/exportar?estado=open")
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) == 2  # header + 1 row

    @pytest.mark.asyncio
    async def test_csv_headers(self, client, session):
        resp = await client.get("/api/stats/alerts/exportar")
        assert resp.status_code == 200
        header = resp.text.strip().split("\n")[0]
        expected_cols = [
            "id",
            "titulo",
            "severidad",
            "estado",
            "eventos",
            "creada",
            "resuelta",
            "descripcion",
        ]
        for col in expected_cols:
            assert col in header
