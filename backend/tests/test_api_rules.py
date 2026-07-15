"""Tests for api/rules.py endpoints — 48% coverage.

Covers: GET /rules, GET /rules/{id}, POST /rules, PUT /rules/{id},
        DELETE /rules/{id}
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.auth_service import AuthService
from app.services.rule_service import RuleService


def _regla_payload() -> dict:
    return {
        "title": "API Rules Test",
        "description": "Test rule for rules API",
        "severity": "medium",
        "status": "active",
        "conditions": {"operator": "AND", "conditions": []},
        "alert_title": "API Rules Alert",
        "alert_severity": "medium",
        "author": "test",
        "tags": [],
        "references": [],
        "false_positives": None,
    }


@pytest_asyncio.fixture
async def admin_user(session):
    service = AuthService(session)
    return await service.crear_usuario("rules_admin", "test123", role="admin")


@pytest_asyncio.fixture
async def analyst_user(session):
    service = AuthService(session)
    return await service.crear_usuario("rules_analyst", "test123", role="analyst")


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


class TestListarReglas:
    @pytest.mark.asyncio
    async def test_listar_vacio(self, client):
        resp = await client.get("/api/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reglas"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_listar_con_datos(self, client, session):
        service = RuleService(session)
        await service.crear_regla(_regla_payload())

        resp = await client.get("/api/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["reglas"]) == 1
        assert data["reglas"][0]["title"] == "API Rules Test"

    @pytest.mark.asyncio
    async def test_listar_campos_respuesta(self, client, session):
        service = RuleService(session)
        await service.crear_regla(_regla_payload())

        resp = await client.get("/api/rules")
        r = resp.json()["reglas"][0]
        for field in [
            "id",
            "title",
            "description",
            "severity",
            "status",
            "conditions",
            "correlation_window",
            "alert_title",
            "alert_severity",
            "tags",
            "created_at",
        ]:
            assert field in r

    @pytest.mark.asyncio
    async def test_listar_filtro_estado(self, client, session):
        service = RuleService(session)
        d = _regla_payload()
        await service.crear_regla(d)
        d2 = _regla_payload()
        d2["title"] = "Disabled"
        d2["status"] = "disabled"
        await service.crear_regla(d2)

        resp = await client.get("/api/rules?estado=active")
        assert resp.json()["total"] == 1
        assert resp.json()["reglas"][0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_listar_filtro_severidad(self, client, session):
        service = RuleService(session)
        d = _regla_payload()
        await service.crear_regla(d)
        d2 = _regla_payload()
        d2["title"] = "Critical Rule"
        d2["severity"] = "critical"
        await service.crear_regla(d2)

        resp = await client.get("/api/rules?severidad=critical")
        assert resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_listar_paginacion(self, client, session):
        service = RuleService(session)
        for i in range(5):
            d = _regla_payload()
            d["title"] = f"Rule {i}"
            await service.crear_regla(d)

        resp = await client.get("/api/rules?limite=2&desde=0")
        assert len(resp.json()["reglas"]) == 2
        assert resp.json()["total"] == 5


class TestObtenerRegla:
    @pytest.mark.asyncio
    async def test_obtener_por_id(self, client, session):
        service = RuleService(session)
        regla = await service.crear_regla(_regla_payload())

        resp = await client.get(f"/api/rules/{regla.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(regla.id)
        assert data["title"] == "API Rules Test"
        for field in [
            "references",
            "false_positives",
            "updated_at",
        ]:
            assert field in data

    @pytest.mark.asyncio
    async def test_obtener_404(self, client):
        resp = await client.get("/api/rules/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
        assert "detail" in resp.json()


class TestCrearRegla:
    @pytest.mark.asyncio
    async def test_crear_regla_ok(self, admin_client):
        resp = admin_client
        payload = _regla_payload()
        r = await resp.post("/api/rules", json=payload)
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == "API Rules Test"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_crear_regla_401_sin_auth(self, client):
        resp = await client.post("/api/rules", json=_regla_payload())
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_crear_regla_403_no_admin(self, analyst_client):
        resp = await analyst_client.post("/api/rules", json=_regla_payload())
        assert resp.status_code == 403


class TestActualizarRegla:
    @pytest.mark.asyncio
    async def test_actualizar_ok(self, admin_client, session):
        service = RuleService(session)
        regla = await service.crear_regla(_regla_payload())

        payload = _regla_payload()
        payload["title"] = "Updated Title"
        resp = await admin_client.put(f"/api/rules/{regla.id}", json=payload)
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_actualizar_404(self, admin_client):
        resp = await admin_client.put(
            "/api/rules/00000000-0000-0000-0000-000000000000",
            json=_regla_payload(),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_actualizar_403_no_admin(self, analyst_client, session):
        service = RuleService(session)
        regla = await service.crear_regla(_regla_payload())
        resp = await analyst_client.put(f"/api/rules/{regla.id}", json=_regla_payload())
        assert resp.status_code == 403


class TestEliminarRegla:
    @pytest.mark.asyncio
    async def test_eliminar_ok(self, admin_client, session):
        service = RuleService(session)
        regla = await service.crear_regla(_regla_payload())
        resp = await admin_client.delete(f"/api/rules/{regla.id}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_eliminar_404(self, admin_client):
        resp = await admin_client.delete(
            "/api/rules/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_eliminar_403_no_admin(self, analyst_client, session):
        service = RuleService(session)
        regla = await service.crear_regla(_regla_payload())
        resp = await analyst_client.delete(f"/api/rules/{regla.id}")
        assert resp.status_code == 403
