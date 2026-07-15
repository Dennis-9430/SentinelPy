"""Tests for api/users.py endpoints — 51% coverage.

Covers: GET /users, POST /users, PATCH /users/{id}/desactivar
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.auth_service import AuthService


@pytest_asyncio.fixture
async def admin_user(session):
    service = AuthService(session)
    return await service.crear_usuario("users_admin", "test123", role="admin")


@pytest_asyncio.fixture
async def analyst_user(session):
    service = AuthService(session)
    return await service.crear_usuario("users_analyst", "test123", role="analyst")


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


class TestListarUsuarios:
    @pytest.mark.asyncio
    async def test_listar_ok(self, admin_client, admin_user):
        resp = await admin_client.get("/api/users")
        assert resp.status_code == 200
        data = resp.json()
        assert "usuarios" in data
        assert data["total"] >= 1
        usernames = [u["username"] for u in data["usuarios"]]
        assert "users_admin" in usernames

    @pytest.mark.asyncio
    async def test_listar_campos(self, admin_client, admin_user):
        resp = await admin_client.get("/api/users")
        u = resp.json()["usuarios"][0]
        for field in ["id", "username", "role", "active", "created_at"]:
            assert field in u

    @pytest.mark.asyncio
    async def test_listar_401_sin_auth(self, client):
        resp = await client.get("/api/users")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_listar_403_no_admin(self, analyst_client):
        resp = await analyst_client.get("/api/users")
        assert resp.status_code == 403


class TestCrearUsuario:
    @pytest.mark.asyncio
    async def test_crear_ok(self, admin_client):
        resp = await admin_client.post(
            "/api/users",
            json={"username": "new_user", "password": "pass123456", "role": "analyst"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "new_user"
        assert data["role"] == "analyst"

    @pytest.mark.asyncio
    async def test_crear_duplicado_409(self, admin_client, admin_user):
        resp = await admin_client.post(
            "/api/users",
            json={
                "username": "users_admin",
                "password": "pass123456",
                "role": "analyst",
            },
        )
        assert resp.status_code == 409
        assert "detail" in resp.json()

    @pytest.mark.asyncio
    async def test_crear_401_sin_auth(self, client):
        resp = await client.post(
            "/api/users",
            json={"username": "no_auth", "password": "pass123456"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_crear_403_no_admin(self, analyst_client):
        resp = await analyst_client.post(
            "/api/users",
            json={"username": "should_fail", "password": "pass123456"},
        )
        assert resp.status_code == 403


class TestDesactivarUsuario:
    @pytest.mark.asyncio
    async def test_desactivar_ok(self, admin_client, session):
        service = AuthService(session)
        user = await service.crear_usuario("to_deactivate", "pass123456")

        resp = await admin_client.patch(f"/api/users/{user.id}/desactivar")
        assert resp.status_code == 200
        assert "desactivado" in resp.json()["mensaje"]

    @pytest.mark.asyncio
    async def test_desactivar_no_puede_a_si_mismo(self, admin_client, admin_user):
        resp = await admin_client.patch(f"/api/users/{admin_user.id}/desactivar")
        assert resp.status_code == 400
        assert "mismo" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_desactivar_404(self, admin_client):
        resp = await admin_client.patch(
            "/api/users/00000000-0000-0000-0000-000000000000/desactivar"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_desactivar_401_sin_auth(self, client, session):
        service = AuthService(session)
        user = await service.crear_usuario("no_auth_target", "pass123456")
        resp = await client.patch(f"/api/users/{user.id}/desactivar")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_desactivar_403_no_admin(self, analyst_client, session):
        service = AuthService(session)
        user = await service.crear_usuario("admin_target", "pass123456")
        resp = await analyst_client.patch(f"/api/users/{user.id}/desactivar")
        assert resp.status_code == 403
