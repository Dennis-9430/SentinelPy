"""Tests unitarios para el servicio de autenticación.

Usa httpx con ASGITransport para testear los endpoints sin levantar servidor.
Para los tests de AuthService se usa pytest-asyncio con sesiones mock.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4
from datetime import datetime, timezone

from app.config import settings
from app.services.auth_service import AuthService
from app.models.user import User


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_mock_result(scalar_return):
    """Crea un mock de Result de SQLAlchemy con scalar_one_or_none."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_return
    return result


def _make_async_execute(session, return_value):
    """Configura session.execute como async function que retorna return_value."""
    async def mock_execute(*args, **kwargs):
        return return_value
    session.execute = mock_execute


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_session():
    """Fixture que provee una sesión async mockeada de SQLAlchemy."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def auth_service(mock_session):
    """Fixture que provee un AuthService con sesión mockeada."""
    return AuthService(mock_session)


@pytest.fixture
def sample_user():
    """Fixture que provee un usuario de prueba."""
    user = User(
        id=uuid4(),
        username="analyst",
        hashed_password=AuthService.hash_password("pass123"),
        role="analyst",
        active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return user


# ── Tests de AuthService ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_crear_usuario(auth_service, mock_session):
    """Verifica que crear_usuario cree el usuario y lo retorne."""
    _make_async_execute(mock_session, _make_mock_result(None))

    # Mock refresh para setear el id
    async def mock_refresh(user):
        user.id = uuid4()
    mock_session.refresh.side_effect = mock_refresh

    user = await auth_service.crear_usuario(
        username="test_user",
        password="test123",
        role="analyst",
    )

    assert user.username == "test_user"
    assert user.role == "analyst"
    assert user.active is True
    # Verificar que la contraseña está hasheada
    assert user.hashed_password != "test123"
    assert AuthService.verify_password("test123", user.hashed_password) is True
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_autenticar_correcto(auth_service, mock_session, sample_user):
    """Verifica que autenticar devuelva el usuario con credenciales válidas."""
    _make_async_execute(mock_session, _make_mock_result(sample_user))

    user = await auth_service.autenticar("analyst", "pass123")

    assert user is not None
    assert user.username == "analyst"
    assert user.role == "analyst"


@pytest.mark.asyncio
async def test_autenticar_password_incorrecto(auth_service, mock_session, sample_user):
    """Verifica que autenticar devuelva None con password incorrecto."""
    _make_async_execute(mock_session, _make_mock_result(sample_user))

    user = await auth_service.autenticar("analyst", "wrong_password")

    assert user is None


@pytest.mark.asyncio
async def test_autenticar_usuario_inexistente(auth_service, mock_session):
    """Verifica que autenticar devuelva None si el usuario no existe."""
    _make_async_execute(mock_session, _make_mock_result(None))

    user = await auth_service.autenticar("no_existe", "pass123")

    assert user is None


@pytest.mark.asyncio
async def test_autenticar_usuario_inactivo(auth_service, mock_session, sample_user):
    """Verifica que autenticar devuelva None si el usuario está deshabilitado."""
    sample_user.active = False
    _make_async_execute(mock_session, _make_mock_result(sample_user))

    user = await auth_service.autenticar("analyst", "pass123")

    assert user is None


@pytest.mark.asyncio
async def test_crear_token(auth_service, sample_user):
    """Verifica que crear_token genere un JWT válido."""
    token = auth_service.crear_token(sample_user)

    assert token is not None
    assert isinstance(token, str)
    assert len(token.split(".")) == 3  # JWT tiene 3 partes

    # Decodificar y verificar payload
    payload = AuthService.decodificar_token(token, settings.secret_key)
    assert payload is not None
    assert payload["sub"] == str(sample_user.id)
    assert payload["username"] == sample_user.username
    assert payload["role"] == sample_user.role


@pytest.mark.asyncio
async def test_decodificar_token_valido(auth_service, sample_user):
    """Verifica que decodificar_token devuelva el payload de un token válido."""
    token = auth_service.crear_token(sample_user)
    payload = AuthService.decodificar_token(token, settings.secret_key)

    assert payload is not None
    assert payload["sub"] == str(sample_user.id)
    assert payload["username"] == "analyst"


@pytest.mark.asyncio
async def test_decodificar_token_invalido():
    """Verifica que decodificar_token devuelva None con token corrupto."""
    payload = AuthService.decodificar_token("token_invalido", settings.secret_key)
    assert payload is None


@pytest.mark.asyncio
async def test_usuario_duplicado_raise(auth_service, mock_session):
    """Verifica que crear_usuario lance ValueError si el usuario ya existe."""
    _make_async_execute(mock_session, _make_mock_result(MagicMock()))

    with pytest.raises(ValueError, match="ya existe"):
        await auth_service.crear_usuario(
            username="duplicado",
            password="pass123",
        )


@pytest.mark.asyncio
async def test_hash_password_verification():
    """Verifica que hash_password y verify_password funcionen juntos."""
    hashed = AuthService.hash_password("mi_secreto")
    assert AuthService.verify_password("mi_secreto", hashed) is True
    assert AuthService.verify_password("otro_secreto", hashed) is False


# ── Tests de integración HTTP ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check():
    """Verifica que el health endpoint siga funcionando."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_login_page_render():
    """Verifica que la página de login se renderice correctamente."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/login")
        assert resp.status_code == 200
        assert "Iniciar Sesión" in resp.text
        assert "SentinelPy" in resp.text


@pytest.mark.asyncio
async def test_dashboard_redirect_when_not_authenticated():
    """Verifica que el dashboard redirija a /login sin autenticación."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/login"


@pytest.mark.asyncio
async def test_events_redirect_when_not_authenticated():
    """Verifica que /events redirija a /login sin autenticación."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/events", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/login"


@pytest.mark.asyncio
async def test_alerts_redirect_when_not_authenticated():
    """Verifica que /alerts redirija a /login sin autenticación."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/alerts", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/login"


@pytest.mark.asyncio
async def test_rules_redirect_when_not_authenticated():
    """Verifica que /rules redirija a /login sin autenticación."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/rules", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/login"
