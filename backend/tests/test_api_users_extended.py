"""Tests for api/users.py — covering remaining edge cases.

Covers: GET /users list comprehension, POST /users success path,
        PATCH /desactivar success and edge cases
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.auth_service import AuthService


@pytest_asyncio.fixture
async def admin_user(session):
    service = AuthService(session)
    return await service.crear_usuario("users_ext_admin", "test123", role="admin")


@pytest_asyncio.fixture
async def analyst_user(session):
    service = AuthService(session)
    return await service.crear_usuario("users_ext_analyst", "test123", role="analyst")


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


class TestListarUsuariosExtended:
    @pytest.mark.asyncio
    async def test_listar_multiples_usuarios(self, admin_client, session):
        service = AuthService(session)
        await service.crear_usuario("multi_user_1", "pass123456", role="analyst")
        await service.crear_usuario("multi_user_2", "pass123456", role="admin")

        resp = await admin_client.get("/api/users")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 3
        usernames = [u["username"] for u in data["usuarios"]]
        assert "multi_user_1" in usernames
        assert "multi_user_2" in usernames

    @pytest.mark.asyncio
    async def test_listar_campos_completos(self, admin_client, admin_user):
        resp = await admin_client.get("/api/users")
        assert resp.status_code == 200
        usuarios = resp.json()["usuarios"]
        admin_data = next(u for u in usuarios if u["username"] == "users_ext_admin")
        assert admin_data["role"] == "admin"
        assert admin_data["active"] is True
        assert "created_at" in admin_data
        assert "id" in admin_data


class TestCrearUsuarioExtended:
    @pytest.mark.asyncio
    async def test_crear_y_verificar_en_listado(self, admin_client):
        resp = await admin_client.post(
            "/api/users",
            json={"username": "verify_in_list", "password": "pass123456", "role": "analyst"},
        )
        assert resp.status_code == 201
        new_id = resp.json()["id"]

        list_resp = await admin_client.get("/api/users")
        ids = [u["id"] for u in list_resp.json()["usuarios"]]
        assert new_id in ids

    @pytest.mark.asyncio
    async def test_crear_admin_role(self, admin_client):
        resp = await admin_client.post(
            "/api/users",
            json={"username": "new_admin", "password": "pass123456", "role": "admin"},
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "admin"


class TestDesactivarUsuarioExtended:
    @pytest.mark.asyncio
    async def test_desactivar_y_verificar_estado(self, admin_client, session):
        service = AuthService(session)
        user = await service.crear_usuario("deactivate_check", "pass123456")

        resp = await admin_client.patch(f"/api/users/{user.id}/desactivar")
        assert resp.status_code == 200

        list_resp = await admin_client.get("/api/users")
        user_data = next(
            u for u in list_resp.json()["usuarios"] if u["username"] == "deactivate_check"
        )
        assert user_data["active"] is False

    @pytest.mark.asyncio
    async def test_desactivar_no_existe(self, admin_client):
        resp = await admin_client.patch(
            "/api/users/00000000-0000-0000-0000-000000000000/desactivar"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_desactivar_a_si_mismo(self, admin_client, admin_user):
        resp = await admin_client.patch(f"/api/users/{admin_user.id}/desactivar")
        assert resp.status_code == 400
        assert "mismo" in resp.json()["detail"]
