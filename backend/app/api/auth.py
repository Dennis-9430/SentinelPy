"""Endpoints de autenticación: login, logout, perfil."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_session
from app.schemas.user import UserLogin
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(
    datos: UserLogin,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Autentica un usuario y setea cookie JWT.

    Endpoint JSON para clientes de la API. Si las credenciales
    son válidas, crea un JWT y lo guarda en una cookie httpOnly.

    Argumentos:
        datos: Credenciales (username, password).
        response: Response de FastAPI para setear la cookie.

    Retorna:
        Dict con mensaje, username y role.

    Raises:
        HTTPException 401: Si las credenciales son incorrectas.
    """
    service = AuthService(session)
    user = await service.autenticar(datos.username, datos.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )

    token = service.crear_token(user)

    # Cookie httpOnly — segura contra XSS, viaja automáticamente en cada request
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=settings.access_token_expire_minutes * 60,
        samesite="lax",
    )

    return {
        "mensaje": "Login exitoso",
        "username": user.username,
        "role": user.role,
    }


@router.post("/logout")
async def logout(response: Response):
    """Elimina la cookie de autenticación.

    Simplemente borra la cookie access_token del navegador.
    """
    response.delete_cookie(key="access_token")
    return {"mensaje": "Sesión cerrada"}


@router.get("/me", response_model=dict)
async def perfil_actual(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Devuelve los datos del usuario autenticado vía cookie.

    Endpoint que el dashboard usa para verificar sesión.

    Argumentos:
        request: Request de FastAPI para leer cookies.
        session: Sesión de base de datos.

    Retorna:
        Dict con id, username y role del usuario autenticado.

    Raises:
        HTTPException 401: Si no hay sesión activa.
    """
    from app.auth import get_current_user_from_cookie

    user = await get_current_user_from_cookie(request, session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
        )
    return {
        "id": str(user.id),
        "username": user.username,
        "role": user.role,
    }
