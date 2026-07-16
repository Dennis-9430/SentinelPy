"""Tests for api/admin.py endpoints — covering all missing lines.

Covers: GET /admin/agents, POST /admin/agents, PATCH deactivate,
        GET /admin/agents/{id}, PUT /admin/agents/{id},
        DELETE /admin/agents/{id}, POST /admin/agents/desactivar-inactivos
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.agent_service import AgentService
from app.services.auth_service import AuthService


@pytest_asyncio.fixture
async def admin_user(session):
    service = AuthService(session)
    return await service.crear_usuario("admin_admin_api", "test123", role="admin")


@pytest_asyncio.fixture
async def analyst_user(session):
    service = AuthService(session)
    return await service.crear_usuario("analyst_admin_api", "test123", role="analyst")


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


class TestListarAgentes:
    @pytest.mark.asyncio
    async def test_listar_vacio(self, admin_client):
        resp = await admin_client.get("/api/admin/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agents"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_listar_con_datos(self, admin_client, session):
        svc = AgentService(session)
        await svc.crear_agente(name="agent-list-1", hostname="host1.local")

        resp = await admin_client.get("/api/admin/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["agents"]) == 1
        assert data["agents"][0]["name"] == "agent-list-1"

    @pytest.mark.asyncio
    async def test_listar_paginacion(self, admin_client, session):
        svc = AgentService(session)
        for i in range(5):
            await svc.crear_agente(name=f"agent-pag-{i}", hostname=f"host{i}.local")

        resp = await admin_client.get("/api/admin/agents?page=1&per_page=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["agents"]) == 2
        assert data["total"] == 5

    @pytest.mark.asyncio
    async def test_listar_401_sin_auth(self, client):
        resp = await client.get("/api/admin/agents")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_listar_403_no_admin(self, analyst_client):
        resp = await analyst_client.get("/api/admin/agents")
        assert resp.status_code == 403


class TestCrearAgente:
    @pytest.mark.asyncio
    async def test_crear_ok(self, admin_client):
        resp = await admin_client.post(
            "/api/admin/agents",
            json={"name": "new-agent", "hostname": "new-host.local"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "new-agent"
        assert data["hostname"] == "new-host.local"
        assert "api_key_raw" in data
        assert data["api_key_raw"].startswith("spy_")

    @pytest.mark.asyncio
    async def test_crear_duplicado_409(self, admin_client, session):
        svc = AgentService(session)
        await svc.crear_agente(name="dup-agent", hostname="host.local")

        resp = await admin_client.post(
            "/api/admin/agents",
            json={"name": "dup-agent", "hostname": "other.local"},
        )
        assert resp.status_code == 409
        assert "detail" in resp.json()

    @pytest.mark.asyncio
    async def test_crear_401_sin_auth(self, client):
        resp = await client.post(
            "/api/admin/agents",
            json={"name": "no-auth", "hostname": "nohost.local"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_crear_403_no_admin(self, analyst_client):
        resp = await analyst_client.post(
            "/api/admin/agents",
            json={"name": "not-admin", "hostname": "nohost.local"},
        )
        assert resp.status_code == 403


class TestDesactivarAgente:
    @pytest.mark.asyncio
    async def test_desactivar_ok(self, admin_client, session):
        svc = AgentService(session)
        agente, _ = await svc.crear_agente(name="to-deactivate", hostname="host.local")

        resp = await admin_client.patch(f"/api/admin/agents/{agente.id}/deactivate")
        assert resp.status_code == 200
        assert "desactivado" in resp.json()["mensaje"]

    @pytest.mark.asyncio
    async def test_desactivar_404(self, admin_client):
        resp = await admin_client.patch("/api/admin/agents/999999/deactivate")
        assert resp.status_code == 404


class TestObtenerAgente:
    @pytest.mark.asyncio
    async def test_obtener_ok(self, admin_client, session):
        svc = AgentService(session)
        agente, _ = await svc.crear_agente(name="get-agent", hostname="host.local")

        resp = await admin_client.get(f"/api/admin/agents/{agente.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "get-agent"
        assert "api_key_hash" not in data
        assert "api_key_raw" not in data

    @pytest.mark.asyncio
    async def test_obtener_404(self, admin_client):
        resp = await admin_client.get("/api/admin/agents/999999")
        assert resp.status_code == 404


class TestActualizarAgente:
    @pytest.mark.asyncio
    async def test_actualizar_ok(self, admin_client, session):
        svc = AgentService(session)
        agente, _ = await svc.crear_agente(name="upd-agent", hostname="old.host.local")

        resp = await admin_client.put(
            f"/api/admin/agents/{agente.id}",
            json={"name": "updated-agent", "hostname": "new.host.local"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "updated-agent"
        assert data["hostname"] == "new.host.local"

    @pytest.mark.asyncio
    async def test_actualizar_404(self, admin_client):
        resp = await admin_client.put(
            "/api/admin/agents/999999",
            json={"name": "no-exist"},
        )
        assert resp.status_code == 404


class TestEliminarAgente:
    @pytest.mark.asyncio
    async def test_eliminar_ok(self, admin_client, session):
        svc = AgentService(session)
        agente, _ = await svc.crear_agente(name="del-agent", hostname="host.local")

        resp = await admin_client.delete(f"/api/admin/agents/{agente.id}")
        assert resp.status_code == 200
        assert "eliminado" in resp.json()["mensaje"]

    @pytest.mark.asyncio
    async def test_eliminar_404(self, admin_client):
        resp = await admin_client.delete("/api/admin/agents/999999")
        assert resp.status_code == 404


class TestDesactivarInactivos:
    @pytest.mark.asyncio
    async def test_desactivar_inactivos_ok(self, admin_client, session):
        resp = await admin_client.post("/api/admin/agents/desactivar-inactivos")
        assert resp.status_code == 200
        assert "desactivados" in resp.json()

    @pytest.mark.asyncio
    async def test_desactivar_inactivos_con_agentes(self, admin_client, session):
        svc = AgentService(session)
        await svc.crear_agente(name="active-agent", hostname="host.local")

        resp = await admin_client.post("/api/admin/agents/desactivar-inactivos")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["desactivados"], int)
