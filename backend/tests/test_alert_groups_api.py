"""Tests E2E para el endpoint GET /api/alerts/groups.

Usa httpx con ASGITransport para testear FastAPI sin levantar servidor.
Verifica la estructura de respuesta y agrupación de alertas por group_key.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.services.alert_service import AlertService
from app.services.rule_service import RuleService


# ── Helpers ────────────────────────────────────────────────────────────────


def _regla_base() -> dict:
    """Retorna datos mínimos de una regla."""
    return {
        "title": "Port Scan Detection",
        "description": "Regla para test del endpoint groups",
        "severity": "medium",
        "status": "active",
        "conditions": {
            "operator": "AND",
            "conditions": [
                {"field": "event_type", "operator": "eq", "value": "port_scan"},
            ],
        },
        "alert_title": "Port Scan Alert",
        "alert_severity": "medium",
        "correlation_window": 300,
    }


def _alerta_base(rule_id, **overrides) -> dict:
    """Retorna datos mínimos de una alerta."""
    data = {
        "rule_id": rule_id,
        "title": "Port Scan Alert",
        "severity": "medium",
        "description": "Alerta de prueba",
        "status": "open",
        "event_count": 1,
    }
    data.update(overrides)
    return data


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def rule_id(session):
    """Crea una regla y retorna su ID."""
    service = RuleService(session)
    regla = await service.crear_regla(_regla_base())
    return regla.id


@pytest.fixture
def app():
    """Fixture que provee la instancia de la aplicación FastAPI."""
    from app.main import app

    return app


@pytest_asyncio.fixture
async def client(session, app):
    """App FastAPI con dependency override para session de test."""
    from app.database import get_session

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Tests ──────────────────────────────────────────────────────────────────


class TestAlertGroupsEndpoint:
    """Prueba el endpoint GET /api/alerts/groups."""

    @pytest.mark.asyncio
    async def test_returns_empty_groups_when_no_alerts(self, client):
        """Sin alertas, devuelve groups vacío y total 0."""
        resp = await client.get("/api/alerts/groups")
        assert resp.status_code == 200
        data = resp.json()
        assert "groups" in data
        assert "total" in data
        assert data["groups"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_grouped_structure(self, client, session, rule_id):
        """Devuelve estructura agrupada con campos correctos."""
        service = AlertService(session)

        datos = _alerta_base(rule_id)
        datos["group_key"] = f"{rule_id}:172.16.0.1"
        datos["group_name"] = "Port Scan Detection from 172.16.0.1"
        await service.crear_alerta(datos)

        resp = await client.get("/api/alerts/groups")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 1
        group = data["groups"][0]
        assert "group_key" in group
        assert "group_name" in group
        assert "alert_count" in group
        assert "max_severity" in group
        assert "risk_score" in group
        assert "alerts" in group
        assert group["alert_count"] == 1
        assert group["alerts"][0]["group_key"] == f"{rule_id}:172.16.0.1"

    @pytest.mark.asyncio
    async def test_groups_alerts_by_group_key(self, client, session, rule_id):
        """Agrupa correctamente alertas con el mismo group_key."""
        service = AlertService(session)

        for i in range(3):
            datos = _alerta_base(rule_id)
            datos["group_key"] = f"{rule_id}:10.0.0.1"
            datos["group_name"] = "Port Scan Detection from 10.0.0.1"
            await service.crear_alerta(datos)

        resp = await client.get("/api/alerts/groups")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 1
        group = data["groups"][0]
        assert group["alert_count"] == 3
        assert len(group["alerts"]) == 3

    @pytest.mark.asyncio
    async def test_multiple_groups_separated(self, client, session, rule_id):
        """Grupos diferentes se retornan separados."""
        service = AlertService(session)

        for _ in range(2):
            datos = _alerta_base(rule_id)
            datos["group_key"] = f"{rule_id}:10.0.0.1"
            datos["group_name"] = "Port Scan Detection from 10.0.0.1"
            await service.crear_alerta(datos)

        datos = _alerta_base(rule_id)
        datos["group_key"] = f"{rule_id}:10.0.0.2"
        datos["group_name"] = "Port Scan Detection from 10.0.0.2"
        await service.crear_alerta(datos)

        resp = await client.get("/api/alerts/groups")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 2
        group_keys = {g["group_key"] for g in data["groups"]}
        assert f"{rule_id}:10.0.0.1" in group_keys
        assert f"{rule_id}:10.0.0.2" in group_keys

    @pytest.mark.asyncio
    async def test_max_severity_reflected(self, client, session, rule_id):
        """max_severity refleja la severidad más alta del grupo."""
        service = AlertService(session)

        datos = _alerta_base(rule_id)
        datos["group_key"] = f"{rule_id}:10.0.0.1"
        datos["group_name"] = "Port Scan Detection from 10.0.0.1"
        datos["severity"] = "critical"
        await service.crear_alerta(datos)

        resp = await client.get("/api/alerts/groups")
        assert resp.status_code == 200
        data = resp.json()
        assert data["groups"][0]["max_severity"] == "critical"
