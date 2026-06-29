"""Tests de integración para el endpoint PATCH /api/alerts/{id}/estado.

Verifica autenticación, autorización, transiciones de estado válidas
e inválidas, y persistencia del cambio.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.services.auth_service import AuthService
from app.services.rule_service import RuleService
from app.services.alert_service import AlertService


def _regla_base() -> dict:
    """Retorna datos mínimos de una regla para crear alertas."""
    return {
        "title": "Alerta Endpoint Test Rule",
        "description": "Rule for testing alerts PATCH endpoint",
        "severity": "high",
        "status": "active",
        "conditions": {"operator": "AND", "conditions": []},
        "alert_title": "Test Alert",
        "alert_severity": "high",
        "author": "test",
        "tags": [],
    }


def _alerta_base(rule_id) -> dict:
    """Retorna datos mínimos de una alerta."""
    return {
        "rule_id": rule_id,
        "title": "Alerta de prueba endpoint",
        "severity": "high",
        "description": "Alerta para test del endpoint PATCH",
        "status": "open",
        "event_count": 3,
    }


@pytest_asyncio.fixture
async def admin_user(session):
    """Crea un usuario admin para tests."""
    service = AuthService(session)
    return await service.crear_usuario("alert_admin", "test123", role="admin")


@pytest_asyncio.fixture
async def analyst_user(session):
    """Crea un usuario analyst (sin permisos admin)."""
    service = AuthService(session)
    return await service.crear_usuario("alert_analyst", "test123", role="analyst")


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
async def test_alerta(session):
    """Crea una regla y una alerta de prueba."""
    rule_service = RuleService(session)
    regla = await rule_service.crear_regla(_regla_base())

    alert_service = AlertService(session)
    alerta = await alert_service.crear_alerta(_alerta_base(regla.id))
    return alerta


@pytest_asyncio.fixture
async def client(session):
    """App FastAPI con get_session override para usar DB del testcontainer."""
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


class TestPatchAlertStatusEndpoint:
    """Prueba el endpoint PATCH /api/alerts/{id}/estado."""

    @pytest.mark.asyncio
    async def test_patch_open_to_investigating(
        self, client, test_alerta, admin_token
    ):
        """Transición open → investigating devuelve status actualizado."""
        response = await client.patch(
            f"/api/alerts/{test_alerta.id}/estado",
            json={"status": "investigating"},
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "investigating"
        assert data["id"] == str(test_alerta.id)

    @pytest.mark.asyncio
    async def test_patch_open_to_acknowledged(
        self, client, test_alerta, admin_token
    ):
        """Transición open → acknowledged devuelve status actualizado."""
        response = await client.patch(
            f"/api/alerts/{test_alerta.id}/estado",
            json={"status": "acknowledged"},
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "acknowledged"

    @pytest.mark.asyncio
    async def test_patch_returns_403_for_non_admin(
        self, client, test_alerta, analyst_token
    ):
        """Non-admin recibe 403 Forbidden."""
        response = await client.patch(
            f"/api/alerts/{test_alerta.id}/estado",
            json={"status": "investigating"},
            cookies={"access_token": analyst_token},
        )
        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_patch_returns_404_for_missing_alert(
        self, client, admin_token
    ):
        """Alerta inexistente devuelve 404."""
        response = await client.patch(
            "/api/alerts/00000000-0000-0000-0000-000000000000/estado",
            json={"status": "resolved"},
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_patch_returns_401_without_auth(
        self, client, test_alerta
    ):
        """Sin cookie de acceso devuelve 401."""
        response = await client.patch(
            f"/api/alerts/{test_alerta.id}/estado",
            json={"status": "resolved"},
        )
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_patch_returns_400_for_invalid_status(
        self, client, test_alerta, admin_token
    ):
        """Estado inválido devuelve 400."""
        response = await client.patch(
            f"/api/alerts/{test_alerta.id}/estado",
            json={"status": "invalid_status"},
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_patch_persists_state_change(
        self, session, client, test_alerta, admin_token
    ):
        """El cambio de estado persiste en la base de datos."""
        await client.patch(
            f"/api/alerts/{test_alerta.id}/estado",
            json={"status": "investigating"},
            cookies={"access_token": admin_token},
        )

        service = AlertService(session)
        alerta = await service.obtener_alerta(str(test_alerta.id))
        assert alerta is not None
        assert alerta.status == "investigating"

    @pytest.mark.asyncio
    async def test_patch_with_resolution_notes(
        self, client, test_alerta, admin_token
    ):
        """PATCH con resolution_notes se guarda correctamente."""
        response = await client.patch(
            f"/api/alerts/{test_alerta.id}/estado",
            json={
                "status": "resolved",
                "resolution_notes": "Se investigó y se cerró",
            },
            cookies={"access_token": admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "resolved"
