"""Authentication endpoints: login, logout, profile."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.schemas.user import UserLogin
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(
    datos: UserLogin,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Authenticate a user and set the JWT cookie.

    JSON endpoint for API clients. If the credentials
    are valid, creates a JWT and stores it in an httpOnly cookie.

    Args:
        datos: Credentials (username, password).
        response: FastAPI response used to set the cookie.

    Returns:
        Dict with message, username and role.

    Raises:
        HTTPException 401: If the credentials are incorrect.
    """
    service = AuthService(session)
    user = await service.autenticar(datos.username, datos.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    token = service.crear_token(user)

    # httpOnly cookie — XSS-safe, travels automatically on every request
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=settings.access_token_expire_minutes * 60,
        samesite="lax",
    )

    return {
        "mensaje": "Login successful",
        "username": user.username,
        "role": user.role,
    }


@router.post("/logout")
async def logout():
    """Remove the authentication cookie and redirect to the login page.

    Creates a RedirectResponse to /login and deletes the access_token
    cookie in the same response, so the browser loses the session on redirect.
    """
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="access_token")
    return response


@router.get("/me", response_model=dict)
async def perfil_actual(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Return the data of the user authenticated via cookie.

    Endpoint the dashboard uses to verify the session.

    Args:
        request: FastAPI request used to read cookies.
        session: Database session.

    Returns:
        Dict with id, username and role of the authenticated user.

    Raises:
        HTTPException 401: If there is no active session.
    """
    from app.auth import get_current_user_from_cookie

    user = await get_current_user_from_cookie(request, session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return {
        "id": str(user.id),
        "username": user.username,
        "role": user.role,
    }
