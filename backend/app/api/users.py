"""User administration endpoints (admin only).

Allows listing, creating and deactivating system users.
All endpoints require an authenticated admin role.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_session
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=dict)
async def listar_usuarios(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """List all system users (admin only)."""
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    usuarios = result.scalars().all()

    return {
        "usuarios": [
            {
                "id": str(u.id),
                "username": u.username,
                "role": u.role,
                "active": u.active,
                "created_at": u.created_at.isoformat(),
            }
            for u in usuarios
        ],
        "total": len(usuarios),
    }


@router.post("", response_model=dict, status_code=201)
async def crear_usuario(
    datos: UserCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Create a new user (admin only)."""
    service = AuthService(session)
    try:
        user = await service.crear_usuario(
            username=datos.username,
            password=datos.password,
            role=datos.role,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {
        "id": str(user.id),
        "username": user.username,
        "role": user.role,
    }


@router.patch("/{usuario_id}/desactivar", response_model=dict)
async def desactivar_usuario(
    usuario_id: str,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Deactivate a user (you cannot deactivate yourself).

    Only an admin can deactivate users, and cannot
    deactivate themselves to avoid leaving no admins.
    """
    # Do not allow deactivating yourself
    if usuario_id == str(admin.id):
        raise HTTPException(
            status_code=400,
            detail="You cannot deactivate yourself",
        )

    user = await session.get(User, UUID(usuario_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.active = False
    await session.commit()

    return {"mensaje": f"User '{user.username}' deactivated"}
