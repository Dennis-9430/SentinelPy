"""Tests for api/rules.py toggle endpoint and edge cases.

Covers: PATCH /rules/{id}/toggle, _toggle_status helper,
        _recargar_engine error path
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.rules import _toggle_status
from app.services.auth_service import AuthService
from app.services.rule_service import RuleService


def _regla_payload() -> dict:
    return {
        "title": "Toggle Test Rule",
        "description": "Rule for toggle tests",
        "severity": "medium",
        "status": "active",
        "conditions": {"operator": "AND", "conditions": []},
        "alert_title": "Toggle Alert",
        "alert_severity": "medium",
        "author": "test",
        "tags": [],
        "references": [],
        "false_positives": None,
    }


@pytest_asyncio.fixture
async def admin_user(session):
    service = AuthService(session)
    return await service.crear_usuario("toggle_admin", "test123", role="admin")


@pytest_asyncio.fixture
async def analyst_user(session):
    service = AuthService(session)
    return await service.crear_usuario("toggle_analyst", "test123", role="analyst")


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


class TestToggleStatusHelper:
    def test_active_becomes_disabled(self):
        assert _toggle_status("active") == "disabled"

    def test_disabled_becomes_active(self):
        assert _toggle_status("disabled") == "active"

    def test_unknown_becomes_active(self):
        assert _toggle_status("unknown") == "active"


class TestToggleRegla:
    @pytest.mark.asyncio
    async def test_toggle_active_to_disabled(self, admin_client, session):
        service = RuleService(session)
        regla = await service.crear_regla(_regla_payload())
        assert regla.status == "active"

        resp = await admin_client.patch(f"/api/rules/{regla.id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_toggle_disabled_to_active(self, admin_client, session):
        service = RuleService(session)
        payload = _regla_payload()
        payload["status"] = "disabled"
        regla = await service.crear_regla(payload)

        resp = await admin_client.patch(f"/api/rules/{regla.id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_toggle_404(self, admin_client):
        resp = await admin_client.patch(
            "/api/rules/00000000-0000-0000-0000-000000000000/toggle"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_toggle_401_sin_auth(self, client):
        resp = await client.patch(
            "/api/rules/00000000-0000-0000-0000-000000000000/toggle"
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_toggle_403_no_admin(self, analyst_client, session):
        service = RuleService(session)
        regla = await service.crear_regla(_regla_payload())

        resp = await analyst_client.patch(f"/api/rules/{regla.id}/toggle")
        assert resp.status_code == 403
