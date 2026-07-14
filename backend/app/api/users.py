"""Endpoints de administración de usuarios (solo admin).

Permite listar, crear y desactivar usuarios del sistema.
Todos los endpoints requieren rol admin autenticado.
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
    """Lista todos los usuarios del sistema (solo admin)."""
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
    """Crea un nuevo usuario (solo admin)."""
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
    """Desactiva un usuario (no se puede desactivar a uno mismo).

    Solo un admin puede desactivar usuarios, y no puede
    desactivarse a sí mismo para evitar quedar sin admins.
    """
    # No permitir desactivarse a sí mismo
    if usuario_id == str(admin.id):
        raise HTTPException(
            status_code=400,
            detail="No puedes desactivarte a ti mismo",
        )

    user = await session.get(User, UUID(usuario_id))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.active = False
    await session.commit()

    return {"mensaje": f"Usuario '{user.username}' desactivado"}
