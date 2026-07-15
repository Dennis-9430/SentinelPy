"""Tests for api/auth.py endpoints — 52% coverage.

Covers: POST /auth/login, POST /auth/logout, GET /auth/me
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.auth_service import AuthService


@pytest_asyncio.fixture
async def setup_user(session):
    service = AuthService(session)
    return await service.crear_usuario("auth_api_user", "testpass123", role="analyst")


@pytest_asyncio.fixture
async def admin_user(session):
    service = AuthService(session)
    return await service.crear_usuario("auth_api_admin", "testpass123", role="admin")


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


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_exitoso(self, client, setup_user):
        resp = await client.post(
            "/api/auth/login",
            json={"username": "auth_api_user", "password": "testpass123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "auth_api_user"
        assert data["role"] == "analyst"
        assert "access_token" in resp.cookies

    @pytest.mark.asyncio
    async def test_login_password_incorrecta(self, client, setup_user):
        resp = await client.post(
            "/api/auth/login",
            json={"username": "auth_api_user", "password": "wrongpass"},
        )
        assert resp.status_code == 401
        assert "detail" in resp.json()

    @pytest.mark.asyncio
    async def test_login_usuario_inexistente(self, client):
        resp = await client.post(
            "/api/auth/login",
            json={"username": "no_existe", "password": "pass123"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_setea_cookie(self, client, setup_user):
        resp = await client.post(
            "/api/auth/login",
            json={"username": "auth_api_user", "password": "testpass123"},
        )
        assert "access_token" in resp.cookies
        cookie = resp.cookies["access_token"]
        assert len(cookie) > 0


class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_redirect(self, client):
        resp = await client.post("/api/auth/logout", follow_redirects=False)
        assert resp.status_code == 303
        assert "/login" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_logout_borra_cookie(self, client, setup_user):
        login_resp = await client.post(
            "/api/auth/login",
            json={"username": "auth_api_user", "password": "testpass123"},
        )
        assert "access_token" in login_resp.cookies

        logout_resp = await client.post("/api/auth/logout", follow_redirects=False)
        cookie_header = logout_resp.headers.get("set-cookie", "")
        assert "access_token" in cookie_header


class TestPerfilActual:
    @pytest.mark.asyncio
    async def test_me_autenticado(self, client, setup_user):
        login_resp = await client.post(
            "/api/auth/login",
            json={"username": "auth_api_user", "password": "testpass123"},
        )
        token = login_resp.cookies["access_token"]
        client.cookies.set("access_token", token)

        resp = await client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "auth_api_user"
        assert data["role"] == "analyst"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_me_no_autenticado(self, client):
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_token_invalido(self, client):
        client.cookies.set("access_token", "token_corrupto")
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_usuario_admin(self, client, admin_user):
        login_resp = await client.post(
            "/api/auth/login",
            json={"username": "auth_api_admin", "password": "testpass123"},
        )
        token = login_resp.cookies["access_token"]
        client.cookies.set("access_token", token)

        resp = await client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"
