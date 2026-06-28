"""Tests de integración para AuthService con PostgreSQL real.

Verifica registro de usuarios, autenticación, y manejo de
usuarios activos/inactivos contra base de datos real.
"""

import pytest
from uuid import UUID

from app.services.auth_service import AuthService


class TestCrearUsuario:
    """Prueba creación de usuarios en base de datos real."""

    @pytest.mark.asyncio
    async def test_crear_usuario_simple(self, session):
        """Crea usuario y verifica persistencia con password hasheada."""
        service = AuthService(session)
        user = await service.crear_usuario(
            username="test_user",
            password="test123",
            role="analyst",
        )

        assert user.id is not None
        assert isinstance(user.id, UUID)
        assert user.username == "test_user"
        assert user.role == "analyst"
        assert user.active is True
        assert user.hashed_password != "test123"  # hasheada
        assert AuthService.verify_password("test123", user.hashed_password) is True
        assert user.created_at is not None

    @pytest.mark.asyncio
    async def test_crear_admin(self, session):
        """Crea usuario admin."""
        service = AuthService(session)
        user = await service.crear_usuario(
            username="admin_user",
            password="admin123",
            role="admin",
        )

        assert user.role == "admin"

    @pytest.mark.asyncio
    async def test_crear_usuario_duplicado_raise(self, session):
        """Crear usuario con username existente lanza ValueError."""
        service = AuthService(session)
        await service.crear_usuario("duplicado", "pass123")

        with pytest.raises(ValueError, match="ya existe"):
            await service.crear_usuario("duplicado", "otra_pass")

    @pytest.mark.asyncio
    async def test_crear_usuario_normaliza_minusculas(self, session):
        """El username se normaliza a minúsculas sin espacios."""
        service = AuthService(session)
        user = await service.crear_usuario("  Usuario_TEST  ", "pass123")

        assert user.username == "usuario_test"


class TestAutenticar:
    """Prueba el flujo completo de autenticación."""

    @pytest.mark.asyncio
    async def test_autenticar_correcto(self, session):
        """Autenticar con credenciales válidas devuelve el usuario."""
        service = AuthService(session)
        await service.crear_usuario("auth_user", "mi_password")

        user = await service.autenticar("auth_user", "mi_password")

        assert user is not None
        assert user.username == "auth_user"

    @pytest.mark.asyncio
    async def test_autenticar_password_incorrecto(self, session):
        """Password incorrecto devuelve None."""
        service = AuthService(session)
        await service.crear_usuario("user_pass", "pass_correcta")

        user = await service.autenticar("user_pass", "pass_incorrecta")

        assert user is None

    @pytest.mark.asyncio
    async def test_autenticar_usuario_inexistente(self, session):
        """Usuario que no existe devuelve None."""
        service = AuthService(session)
        user = await service.autenticar("no_existe", "pass123")

        assert user is None

    @pytest.mark.asyncio
    async def test_autenticar_normaliza_username(self, session):
        """Autenticar también normaliza el username."""
        service = AuthService(session)
        await service.crear_usuario("CaseUser", "pass123")

        user = await service.autenticar("  caseuser  ", "pass123")
        assert user is not None


class TestUsuarioInactivo:
    """Prueba manejo de usuarios desactivados."""

    @pytest.mark.asyncio
    async def test_usuario_inactivo_no_autentica(self, session):
        """Usuario con active=False no puede autenticarse."""
        service = AuthService(session)
        user = await service.crear_usuario("inactive_user", "pass123")

        # Desactivar usuario directamente
        user.active = False
        await session.commit()

        result = await service.autenticar("inactive_user", "pass123")
        assert result is None

    @pytest.mark.asyncio
    async def test_usuario_activo_si_autentica(self, session):
        """Usuario activo puede autenticarse normalmente."""
        service = AuthService(session)
        await service.crear_usuario("active_user", "pass123")

        user = await service.autenticar("active_user", "pass123")
        assert user is not None
        assert user.active is True


class TestCRUDUsuarios:
    """Prueba operaciones adicionales de usuarios."""

    @pytest.mark.asyncio
    async def test_obtener_por_id(self, session):
        """Obtener usuario por UUID."""
        service = AuthService(session)
        creado = await service.crear_usuario("get_by_id", "pass123")

        obtenido = await service.obtener_por_id(creado.id)

        assert obtenido is not None
        assert obtenido.username == "get_by_id"

    @pytest.mark.asyncio
    async def test_obtener_por_id_inexistente(self, session):
        """Obtener usuario con UUID que no existe devuelve None."""
        from uuid import UUID
        service = AuthService(session)

        user = await service.obtener_por_id(UUID("00000000-0000-0000-0000-000000000000"))
        assert user is None


class TestJWT:
    """Prueba generación y verificación de tokens JWT (no requieren BD)."""

    @pytest.mark.asyncio
    async def test_crear_y_decodificar_token(self, session):
        """Crea un token JWT y lo decodifica correctamente."""
        from app.models.user import User
        from app.config import settings

        user = User(username="jwt_user", role="admin")
        service = AuthService(session)

        token = service.crear_token(user)

        assert token is not None
        assert len(token.split(".")) == 3

        payload = AuthService.decodificar_token(token, settings.secret_key)
        assert payload is not None
        assert payload["username"] == "jwt_user"
        assert payload["role"] == "admin"

    @pytest.mark.asyncio
    async def test_decodificar_token_invalido(self, session):
        """Token corrupto devuelve None."""
        payload = AuthService.decodificar_token("token_invalido", "secret")
        assert payload is None
