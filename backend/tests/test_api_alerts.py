"""Tests for api/alerts.py endpoints — 56% coverage.

Covers: GET /alerts, GET /alerts/groups, GET /alerts/{id},
        GET /alerts/estadisticas
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.alert_service import AlertService
from app.services.auth_service import AuthService
from app.services.rule_service import RuleService


def _regla_base() -> dict:
    return {
        "title": "Alerts API Test Rule",
        "description": "Rule for alerts API tests",
        "severity": "high",
        "status": "active",
        "conditions": {"operator": "AND", "conditions": []},
        "alert_title": "API Alert",
        "alert_severity": "high",
    }


def _alerta_base(rule_id) -> dict:
    return {
        "rule_id": rule_id,
        "title": "Alerta API test",
        "severity": "high",
        "description": "Alerta para test del API de alertas",
        "status": "open",
        "event_count": 2,
    }


@pytest_asyncio.fixture
async def admin_user(session):
    service = AuthService(session)
    return await service.crear_usuario("alerts_api_admin", "test123", role="admin")


@pytest_asyncio.fixture
async def admin_token(admin_user, session):
    service = AuthService(session)
    return service.crear_token(admin_user)


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
async def admin_client(client, admin_token):
    client.cookies.set("access_token", admin_token)
    return client


class TestListarAlertas:
    @pytest.mark.asyncio
    async def test_listar_vacio(self, client):
        resp = await client.get("/api/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["alertas"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_listar_con_datos(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        await alert_svc.crear_alerta(_alerta_base(regla.id))

        resp = await client.get("/api/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["alertas"]) == 1

    @pytest.mark.asyncio
    async def test_listar_filtro_estado(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        a = _alerta_base(regla.id)
        await alert_svc.crear_alerta(a)
        a2 = _alerta_base(regla.id)
        a2["status"] = "resolved"
        await alert_svc.crear_alerta(a2)

        resp = await client.get("/api/alerts?estado=open")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["alertas"][0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_listar_filtro_severidad(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        a1 = _alerta_base(regla.id)
        a1["severity"] = "high"
        await alert_svc.crear_alerta(a1)
        a2 = _alerta_base(regla.id)
        a2["severity"] = "low"
        await alert_svc.crear_alerta(a2)

        resp = await client.get("/api/alerts?severidad=low")
        assert resp.json()["total"] == 1
        assert resp.json()["alertas"][0]["severity"] == "low"

    @pytest.mark.asyncio
    async def test_listar_campos(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        await alert_svc.crear_alerta(_alerta_base(regla.id))

        resp = await client.get("/api/alerts")
        a = resp.json()["alertas"][0]
        for field in [
            "id",
            "rule_id",
            "title",
            "severity",
            "description",
            "status",
            "event_count",
            "created_at",
        ]:
            assert field in a


class TestObtenerAlerta:
    @pytest.mark.asyncio
    async def test_obtener_por_id(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        alerta = await alert_svc.crear_alerta(_alerta_base(regla.id))

        resp = await client.get(f"/api/alerts/{alerta.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(alerta.id)
        assert data["title"] == "Alerta API test"

    @pytest.mark.asyncio
    async def test_obtener_404(self, client):
        resp = await client.get("/api/alerts/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


class TestListarGruposAlertas:
    @pytest.mark.asyncio
    async def test_grupos_vacio(self, client):
        resp = await client.get("/api/alerts/groups")
        assert resp.status_code == 200
        data = resp.json()
        assert data["groups"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_grupos_con_alertas(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)

        a1 = _alerta_base(regla.id)
        a1["group_key"] = f"{regla.id}:10.0.0.1"
        a1["group_name"] = "Test Group"
        await alert_svc.crear_alerta(a1)

        a2 = _alerta_base(regla.id)
        a2["group_key"] = f"{regla.id}:10.0.0.1"
        a2["group_name"] = "Test Group"
        await alert_svc.crear_alerta(a2)

        resp = await client.get("/api/alerts/groups")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["groups"][0]["alert_count"] == 2

    @pytest.mark.asyncio
    async def test_grupos_ignora_resueltas(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)

        a = _alerta_base(regla.id)
        a["group_key"] = f"{regla.id}:10.0.0.1"
        created = await alert_svc.crear_alerta(a)
        await alert_svc.actualizar_estado(str(created.id), "resolved")

        resp = await client.get("/api/alerts/groups")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestEstadisticasAlertas:
    @pytest.mark.asyncio
    async def test_estadisticas_vacio(self, client):
        resp = await client.get("/api/alerts/estadisticas")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_alertas" in data
        assert "alertas_abiertas" in data
        assert "alertas_resueltas" in data

    @pytest.mark.asyncio
    async def test_estadisticas_con_datos(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)

        a1 = _alerta_base(regla.id)
        a1["status"] = "open"
        await alert_svc.crear_alerta(a1)

        a2 = _alerta_base(regla.id)
        a2["status"] = "resolved"
        await alert_svc.crear_alerta(a2)

        resp = await client.get("/api/alerts/estadisticas")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_alertas"] == 2
        assert data["alertas_abiertas"] == 1
        assert data["alertas_resueltas"] == 1
