"""Tests for api/alerts.py PATCH update status and groups edge cases.

Covers: PATCH /alerts/{id}/estado, groups with risk_score and max_severity
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.alert_service import AlertService
from app.services.auth_service import AuthService
from app.services.rule_service import RuleService


def _regla_base() -> dict:
    return {
        "title": "Alert Update Test Rule",
        "description": "Rule for alert update tests",
        "severity": "high",
        "status": "active",
        "conditions": {"operator": "AND", "conditions": []},
        "alert_title": "Update Alert",
        "alert_severity": "high",
    }


def _alerta_base(rule_id) -> dict:
    return {
        "rule_id": rule_id,
        "title": "Alerta update test",
        "severity": "high",
        "description": "Alerta para test de update",
        "status": "open",
        "event_count": 2,
    }


@pytest_asyncio.fixture
async def admin_user(session):
    service = AuthService(session)
    return await service.crear_usuario("alert_update_admin", "test123", role="admin")


@pytest_asyncio.fixture
async def analyst_user(session):
    service = AuthService(session)
    return await service.crear_usuario(
        "alert_update_analyst", "test123", role="analyst"
    )


@pytest_asyncio.fixture
async def admin_token(admin_user, session):
    service = AuthService(session)
    return service.crear_token(admin_user)


@pytest_asyncio.fixture
async def analyst_token(analyst_user, session):
    service = AuthService(session)
    return service.crear_token(analyst_user)


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


@pytest_asyncio.fixture
async def analyst_client(client, analyst_token):
    client.cookies.set("access_token", analyst_token)
    return client


class TestActualizarEstadoAlerta:
    @pytest.mark.asyncio
    async def test_update_to_acknowledged(self, admin_client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        alerta = await alert_svc.crear_alerta(_alerta_base(regla.id))

        resp = await admin_client.patch(
            f"/api/alerts/{alerta.id}/estado",
            json={"status": "acknowledged"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "acknowledged"
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_update_to_resolved(self, admin_client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        alerta = await alert_svc.crear_alerta(_alerta_base(regla.id))

        resp = await admin_client.patch(
            f"/api/alerts/{alerta.id}/estado",
            json={"status": "resolved", "resolution_notes": "False alarm"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "resolved"
        assert data["resolved_at"] is not None

    @pytest.mark.asyncio
    async def test_update_to_false_positive(self, admin_client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        alerta = await alert_svc.crear_alerta(_alerta_base(regla.id))

        resp = await admin_client.patch(
            f"/api/alerts/{alerta.id}/estado",
            json={"status": "false_positive"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "false_positive"

    @pytest.mark.asyncio
    async def test_update_invalid_status(self, admin_client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        alerta = await alert_svc.crear_alerta(_alerta_base(regla.id))

        resp = await admin_client.patch(
            f"/api/alerts/{alerta.id}/estado",
            json={"status": "invalid_status"},
        )
        assert resp.status_code == 400
        assert "detail" in resp.json()

    @pytest.mark.asyncio
    async def test_update_404(self, admin_client):
        resp = await admin_client.patch(
            "/api/alerts/00000000-0000-0000-0000-000000000000/estado",
            json={"status": "resolved"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_401_sin_auth(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        alerta = await alert_svc.crear_alerta(_alerta_base(regla.id))

        resp = await client.patch(
            f"/api/alerts/{alerta.id}/estado",
            json={"status": "resolved"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_update_403_no_admin(self, analyst_client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)
        alerta = await alert_svc.crear_alerta(_alerta_base(regla.id))

        resp = await analyst_client.patch(
            f"/api/alerts/{alerta.id}/estado",
            json={"status": "resolved"},
        )
        assert resp.status_code == 403


class TestGruposConRiskScore:
    @pytest.mark.asyncio
    async def test_grupos_risk_score(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)

        a1 = _alerta_base(regla.id)
        a1["group_key"] = f"{regla.id}:10.0.0.1"
        a1["group_name"] = "Risk Group"
        a1["risk_score"] = 0.85
        a1["severity"] = "critical"
        await alert_svc.crear_alerta(a1)

        a2 = _alerta_base(regla.id)
        a2["group_key"] = f"{regla.id}:10.0.0.1"
        a2["group_name"] = "Risk Group"
        a2["risk_score"] = 0.45
        a2["severity"] = "low"
        await alert_svc.crear_alerta(a2)

        resp = await client.get("/api/alerts/groups")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        group = data["groups"][0]
        assert group["group_key"] == f"{regla.id}:10.0.0.1"
        assert group["alert_count"] == 2
        assert group["max_severity"] == "critical"
        assert group["risk_score"] is not None

    @pytest.mark.asyncio
    async def test_grupos_without_group_key_excluded(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)

        a = _alerta_base(regla.id)
        await alert_svc.crear_alerta(a)

        resp = await client.get("/api/alerts/groups")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_grupos_multiple_groups(self, client, session):
        rule_svc = RuleService(session)
        regla = await rule_svc.crear_regla(_regla_base())
        alert_svc = AlertService(session)

        for ip in ["10.0.0.1", "10.0.0.2"]:
            a = _alerta_base(regla.id)
            a["group_key"] = f"{regla.id}:{ip}"
            a["group_name"] = f"Group {ip}"
            await alert_svc.crear_alerta(a)

        resp = await client.get("/api/alerts/groups")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2
