"""Dependencias de autenticación para rutas HTML y API.

Incluye helpers para verificar autenticación básica (get_current_user_from_cookie,
require_user) y protección por roles (require_admin, verificar_admin_html).
"""

import logging
from uuid import UUID
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_session
from app.models.user import User
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


async def get_current_user_from_cookie(
    request: Request,
    session: AsyncSession,
):
    """Obtiene el usuario autenticado desde la cookie JWT.

    Se usa en las rutas del dashboard HTML. Lee la cookie access_token,
    decodifica el JWT, y busca el usuario en la base de datos.

    Argumentos:
        request: Request de FastAPI para leer cookies.
        session: Sesión asíncrona de SQLAlchemy.

    Retorna:
        User si el token es válido, None en caso contrario.
    """
    token = request.cookies.get("access_token")
    if not token:
        return None

    payload = AuthService.decodificar_token(token, settings.secret_key)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    service = AuthService(session)
    user = await service.obtener_por_id(UUID(user_id))
    return user


async def require_user(
    request: Request,
    session: AsyncSession,
):
    """Middleware para rutas que requieren autenticación.

    Si el usuario no está autenticado, devuelve (None, RedirectResponse)
    para redirigir al login. Si está autenticado, devuelve (user, None).

    Argumentos:
        request: Request de FastAPI.
        session: Sesión asíncrona de SQLAlchemy.

    Retorna:
        Tupla (user | None, RedirectResponse | None).
    """
    user = await get_current_user_from_cookie(request, session)
    if not user:
        return None, RedirectResponse(url="/login")
    return user, None


async def require_admin(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Dependency para rutas API — requiere usuario admin autenticado.

    Lee la cookie JWT, verifica el token, busca el usuario en BD,
    y verifica que tenga rol 'admin'. Si algo falla, lanza HTTPException.

    Uso en rutas API:
        @router.post("/rules")
        async def crear_regla(..., admin: User = Depends(require_admin)):

    Retorna:
        La instancia de User si es admin autenticado.

    Raises:
        HTTPException 401: Si no hay token, es inválido, o el usuario
                           no existe o está desactivado.
        HTTPException 403: Si el usuario no tiene rol admin.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
        )

    payload = AuthService.decodificar_token(token, settings.secret_key)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token mal formado",
        )

    service = AuthService(session)
    user = await service.obtener_por_id(UUID(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario desactivado",
        )
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol administrador",
        )

    return user


async def verificar_admin_html(
    request: Request,
    session: AsyncSession,
) -> User | None:
    """Verifica admin para rutas HTML. Devuelve User o None.

    Es una versión no-dependency de require_admin para usar en
    rutas de templates donde no se puede usar Depends().
    """
    user = await get_current_user_from_cookie(request, session)
    if not user or user.role != "admin":
        return None
    return user
