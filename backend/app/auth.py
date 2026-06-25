"""Dependencias de autenticación para rutas HTML y API."""

import logging
from uuid import UUID
from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
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
