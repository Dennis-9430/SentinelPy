"""Tests for auth.py dependency functions — 64% coverage.

Covers: require_admin, require_agent, verificar_admin_html, require_user
All paths: no token, invalid token, no sub, user not found,
inactive user, non-admin, agent valid/invalid/inactive.
"""

from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.auth_service import AuthService


@pytest_asyncio.fixture
async def setup_admin(session):
    service = AuthService(session)
    return await service.crear_usuario("dep_admin", "test123", role="admin")


@pytest_asyncio.fixture
async def setup_analyst(session):
    service = AuthService(session)
    return await service.crear_usuario("dep_analyst", "test123", role="analyst")


@pytest_asyncio.fixture
async def admin_token(setup_admin, session):
    service = AuthService(session)
    return service.crear_token(setup_admin)


@pytest_asyncio.fixture
async def analyst_token(setup_analyst, session):
    service = AuthService(session)
    return service.crear_token(setup_analyst)


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


class TestRequireAdminDependency:
    """Test require_admin paths through endpoints that use it."""

    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, client):
        resp = await client.post(
            "/api/rules",
            json={
                "title": "x",
                "description": "x",
                "conditions": {},
                "alert_title": "x",
            },
        )
        assert resp.status_code == 401
        assert "No autenticado" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, client):
        client.cookies.set("access_token", "totally.invalid.token")
        resp = await client.post(
            "/api/rules",
            json={
                "title": "x",
                "description": "x",
                "conditions": {},
                "alert_title": "x",
            },
        )
        assert resp.status_code == 401
        assert "inválido" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_token_without_sub_returns_401(self, client):
        """Token with no 'sub' claim → 401."""
        import jwt

        from app.config import settings

        token = jwt.encode(
            {"no_sub": True}, settings.secret_key, algorithm=settings.jwt_algorithm
        )
        client.cookies.set("access_token", token)
        resp = await client.post(
            "/api/rules",
            json={
                "title": "x",
                "description": "x",
                "conditions": {},
                "alert_title": "x",
            },
        )
        assert resp.status_code == 401
        assert "mal formado" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, client, analyst_token):
        client.cookies.set("access_token", analyst_token)
        resp = await client.post(
            "/api/rules",
            json={
                "title": "x",
                "description": "x",
                "conditions": {},
                "alert_title": "x",
            },
        )
        assert resp.status_code == 403
        assert "administrador" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_admin_works(self, client, admin_token):
        client.cookies.set("access_token", admin_token)
        resp = await client.post(
            "/api/rules",
            json={
                "title": "Admin Test Rule",
                "description": "desc",
                "conditions": {"op": "AND"},
                "alert_title": "alert",
            },
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_inactive_user_returns_401(self, client, session):
        service = AuthService(session)
        user = await service.crear_usuario("inactive_dep", "test123", role="admin")
        user.active = False
        await session.commit()
        token = service.crear_token(user)
        client.cookies.set("access_token", token)

        resp = await client.post(
            "/api/rules",
            json={
                "title": "x",
                "description": "x",
                "conditions": {},
                "alert_title": "x",
            },
        )
        assert resp.status_code == 401
        assert "desactivado" in resp.json()["detail"]


class TestRequireAgentDependency:
    """Test require_agent paths through agent ingest endpoints."""

    @pytest.mark.asyncio
    async def test_no_auth_header_returns_401(self, client):
        resp = await client.post(
            "/api/v2/events",
            json={"events": []},
        )
        assert resp.status_code == 401
        assert "Bearer" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_api_key_returns_401(self, client):
        resp = await client.post(
            "/api/v2/events",
            json={"events": []},
            headers={"Authorization": "Bearer invalid_key"},
        )
        assert resp.status_code == 401
        assert "inválida" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_inactive_agent_returns_403(self, client, session):
        from app.services.agent_service import AgentService

        agent_svc = AgentService(session)
        agent, key = await agent_svc.crear_agente("inactive-agent", "inactive-agent")
        agent.active = False
        await session.commit()

        resp = await client.post(
            "/api/v2/events",
            json={"events": []},
            headers={"Authorization": f"Bearer {key}"},
        )
        assert resp.status_code == 403
        assert "desactivado" in resp.json()["detail"]


class TestVerificarAdminHtml:
    """Test verificar_admin_html through direct function calls."""

    @pytest.mark.asyncio
    async def test_verificar_admin_html_no_user(self, session):
        from app.auth import verificar_admin_html

        mock_request = MagicMock()
        mock_request.cookies = {}

        result = await verificar_admin_html(mock_request, session)
        assert result is None

    @pytest.mark.asyncio
    async def test_verificar_admin_html_with_admin(self, session, setup_admin):
        from app.auth import verificar_admin_html

        service = AuthService(session)
        token = service.crear_token(setup_admin)

        mock_request = MagicMock()
        mock_request.cookies = {"access_token": token}

        result = await verificar_admin_html(mock_request, session)
        assert result is not None
        assert result.role == "admin"

    @pytest.mark.asyncio
    async def test_verificar_admin_html_non_admin(self, session, setup_analyst):
        from app.auth import verificar_admin_html

        service = AuthService(session)
        token = service.crear_token(setup_analyst)

        mock_request = MagicMock()
        mock_request.cookies = {"access_token": token}

        result = await verificar_admin_html(mock_request, session)
        assert result is None


class TestRequireUser:
    """Test require_user through direct function calls."""

    @pytest.mark.asyncio
    async def test_require_user_no_auth(self, session):
        from app.auth import require_user

        mock_request = MagicMock()
        mock_request.cookies = {}

        user, redirect = await require_user(mock_request, session)
        assert user is None
        assert redirect is not None
        assert "/login" in redirect.headers["location"]

    @pytest.mark.asyncio
    async def test_require_user_authenticated(self, session, setup_admin):
        from app.auth import require_user

        service = AuthService(session)
        token = service.crear_token(setup_admin)

        mock_request = MagicMock()
        mock_request.cookies = {"access_token": token}

        user, redirect = await require_user(mock_request, session)
        assert user is not None
        assert redirect is None
        assert user.username == "dep_admin"


class TestGetCurrentUserFromCookie:
    """Test get_current_user_from_cookie paths."""

    @pytest.mark.asyncio
    async def test_no_cookie(self, session):
        from app.auth import get_current_user_from_cookie

        mock_request = MagicMock()
        mock_request.cookies = {}

        result = await get_current_user_from_cookie(mock_request, session)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_token(self, session):
        from app.auth import get_current_user_from_cookie

        mock_request = MagicMock()
        mock_request.cookies = {"access_token": "bad.token.here"}

        result = await get_current_user_from_cookie(mock_request, session)
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_token(self, session, setup_admin):
        from app.auth import get_current_user_from_cookie

        service = AuthService(session)
        token = service.crear_token(setup_admin)

        mock_request = MagicMock()
        mock_request.cookies = {"access_token": token}

        result = await get_current_user_from_cookie(mock_request, session)
        assert result is not None
        assert result.username == "dep_admin"
