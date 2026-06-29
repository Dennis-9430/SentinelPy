"""Tests de integración para el endpoint PATCH /api/rules/{id}/toggle.

Requiere PostgreSQL via Testcontainers para probar el flujo completo:
autenticación → toggle → respuesta JSON.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.services.auth_service import AuthService
from app.services.rule_service import RuleService


def _regla_activa() -> dict:
    """Retorna un dict con campos mínimos de una regla activa."""
    return {
        "title": "Toggle Test Rule",
        "description": "Rule for testing toggle endpoint",
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


def _regla_desactivada() -> dict:
    """Retorna un dict con una regla en estado disabled."""
    data = _regla_activa()
    data["title"] = "Disabled Rule"
    data["status"] = "disabled"
    return data


@pytest_asyncio.fixture
async def admin_user(session):
    """Crea un usuario admin para tests de toggle."""
    service = AuthService(session)
    return await service.crear_usuario("toggle_admin", "test123", role="admin")


@pytest_asyncio.fixture
async def analyst_user(session):
    """Crea un usuario analyst (sin permisos admin)."""
    service = AuthService(session)
    return await service.crear_usuario("toggle_analyst", "test123", role="analyst")


@pytest_asyncio.fixture
async def admin_token(admin_user, session):
    """Genera un token JWT válido para el admin."""
    service = AuthService(session)
    return service.crear_token(admin_user)


@pytest_asyncio.fixture
async def analyst_token(analyst_user, session):
    """Genera un token JWT válido para el analyst."""
    service = AuthService(session)
    return service.crear_token(analyst_user)


@pytest_asyncio.fixture
async def test_rule(session):
    """Crea una regla activa de prueba."""
    service = RuleService(session)
    return await service.crear_regla(_regla_activa())


@pytest_asyncio.fixture
async def disabled_rule(session):
    """Crea una regla desactivada de prueba."""
    service = RuleService(session)
    return await service.crear_regla(_regla_desactivada())


@pytest_asyncio.fixture
async def client(session):
    """App FastAPI con get_session override para usar DB del testcontainer.

    La sesión se reutiliza para todas las dependencias que llamen
    a get_session (require_admin + route handler).
    """
    from app.main import app
    from app.database import get_session

    async def override_get_session():
        while True:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class TestToggleRuleEndpoint:
    """Prueba el endpoint PATCH /api/rules/{id}/toggle."""

    @pytest.mark.asyncio
    async def test_toggle_active_to_disabled(self, client, test_rule, admin_token):
        """Toggle sobre regla activa → status disabled, 200."""
        response = await client.patch(
            f"/api/rules/{test_rule.id}/toggle",
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_toggle_disabled_to_active(self, client, disabled_rule, admin_token):
        """Toggle sobre regla desactivada → status active, 200."""
        response = await client.patch(
            f"/api/rules/{disabled_rule.id}/toggle",
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_toggle_returns_403_for_non_admin(self, client, test_rule, analyst_token):
        """Non-admin recibe 403 Forbidden."""
        response = await client.patch(
            f"/api/rules/{test_rule.id}/toggle",
            cookies={"access_token": analyst_token},
        )
        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_toggle_returns_404_for_missing_rule(self, client, admin_token):
        """Regla inexistente devuelve 404."""
        response = await client.patch(
            "/api/rules/00000000-0000-0000-0000-000000000000/toggle",
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_toggle_returns_401_without_auth(self, client, test_rule):
        """Sin cookie de acceso devuelve 401."""
        response = await client.patch(
            f"/api/rules/{test_rule.id}/toggle",
        )
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_toggle_persists_state_change(self, session, client, test_rule, admin_token):
        """El cambio de estado persiste en la base de datos."""
        await client.patch(
            f"/api/rules/{test_rule.id}/toggle",
            cookies={"access_token": admin_token},
        )

        service = RuleService(session)
        regla = await service.obtener_regla(str(test_rule.id))
        assert regla is not None
        assert regla.status == "disabled"

        # Toggle again
        await client.patch(
            f"/api/rules/{test_rule.id}/toggle",
            cookies={"access_token": admin_token},
        )
        regla = await service.obtener_regla(str(test_rule.id))
        assert regla.status == "active"
