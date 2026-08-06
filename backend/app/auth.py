"""Authentication dependencies for HTML and API routes.

Includes helpers to verify basic authentication (get_current_user_from_cookie,
require_user), role-based protection (require_admin, verificar_admin_html),
and remote agent authentication via Bearer token (require_agent).
"""

import logging
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models.agent import Agent
from app.models.user import User
from app.services.agent_service import AgentService
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


async def get_current_user_from_cookie(
    request: Request,
    session: AsyncSession,
):
    """Get the authenticated user from the JWT cookie.

    Used on the HTML dashboard routes. Reads the access_token cookie,
    decodes the JWT, and looks up the user in the database.

    Args:
        request: FastAPI request used to read cookies.
        session: Async SQLAlchemy session.

    Returns:
        User if the token is valid, None otherwise.
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
    """Dependency for routes that require authentication.

    If the user is not authenticated, returns (None, RedirectResponse)
    to redirect to the login page. If authenticated, returns (user, None).

    Args:
        request: FastAPI request.
        session: Async SQLAlchemy session.

    Returns:
        Tuple (user | None, RedirectResponse | None).
    """
    user = await get_current_user_from_cookie(request, session)
    if not user:
        return None, RedirectResponse(url="/login")
    return user, None


async def require_admin(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """API route dependency — requires an authenticated admin user.

    Reads the JWT cookie, verifies the token, looks up the user in the DB,
    and checks that they have the 'admin' role. On any failure, raises HTTPException.

    Usage in API routes:
        @router.post("/rules")
        async def crear_regla(..., admin: User = Depends(require_admin)):

    Returns:
        The User instance if it is an authenticated admin.

    Raises:
        HTTPException 401: If there is no token, it is invalid, or the user
                           does not exist or is deactivated.
        HTTPException 403: If the user does not have the admin role.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = AuthService.decodificar_token(token, settings.secret_key)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token",
        )

    service = AuthService(session)
    user = await service.obtener_por_id(UUID(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User deactivated",
        )
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )

    return user


async def verificar_admin_html(
    request: Request,
    session: AsyncSession,
) -> User | None:
    """Verify admin access for HTML routes. Returns User or None.

    A non-dependency version of require_admin for use in template
    routes where Depends() cannot be used.
    """
    user = await get_current_user_from_cookie(request, session)
    if not user or user.role != "admin":
        return None
    return user


async def require_agent(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Agent:
    """Agent route dependency — requires a valid Bearer API key.

    Reads the Authorization header, extracts the Bearer token, and verifies
    it against active agents using bcrypt verify.

    Usage:
        @router.post("/api/v2/events")
        async def ingestar_eventos(..., agent: Agent = Depends(require_agent)):

    Returns:
        The Agent instance if the API key is valid and the agent is active.

    Raises:
        HTTPException 401: If there is no token or it is invalid.
        HTTPException 403: If the agent is deactivated.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
        )

    api_key = auth.removeprefix("Bearer ")
    service = AgentService(session)
    agent = await service.obtener_por_api_key(api_key)

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    if not agent.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent deactivated",
        )

    return agent
