"""Remote agent administration endpoints (admin only).

Allows listing, creating and deactivating agents.
All endpoints require an authenticated admin role.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_session
from app.models.user import User
from app.schemas.agent import (
    AgentCreate,
    AgentCreateResponse,
    AgentList,
    AgentRead,
    AgentUpdate,
)
from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/agents", response_model=AgentList)
async def listar_agentes(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Agents per page"),
):
    """List all registered agents with pagination (active and inactive).

    Only accessible to authenticated administrators.
    Never exposes api_key_hash or api_key_raw.
    """
    service = AgentService(session)
    agentes, total = await service.listar_agentes(
        page=page,
        per_page=per_page,
    )

    return AgentList(
        agents=[AgentRead.model_validate(a) for a in agentes],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/agents", response_model=AgentCreateResponse, status_code=201)
async def crear_agente(
    datos: AgentCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Create a new remote agent with an automatically generated API key.

    The API key is generated with secrets.token_urlsafe(32) and hashed
    with bcrypt before persisting. The plaintext key is returned in
    api_key_raw ONCE — it cannot be retrieved afterwards.
    """
    service = AgentService(session)
    try:
        agente, raw_key = await service.crear_agente(
            name=datos.name,
            hostname=datos.hostname,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return AgentCreateResponse(
        id=agente.id,
        name=agente.name,
        hostname=agente.hostname,
        last_seen=agente.last_seen,
        active=agente.active,
        version=agente.version,
        heartbeat_timeout_minutes=agente.heartbeat_timeout_minutes,
        created_at=agente.created_at,
        updated_at=agente.updated_at,
        api_key_raw=raw_key,
    )


@router.patch("/agents/{agent_id:int}/deactivate", response_model=dict)
async def desactivar_agente(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Deactivate an agent by its ID.

    A deactivated agent cannot authenticate or send events.
    """
    service = AgentService(session)
    desactivado = await service.desactivar_agente(agent_id)

    if not desactivado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    return {"mensaje": f"Agent {agent_id} deactivated"}


@router.get("/agents/{agent_id:int}", response_model=AgentRead)
async def obtener_agente(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Get an agent by its ID.

    Returns all agent fields without exposing api_key_hash.
    """
    service = AgentService(session)
    agente = await service.obtener_por_id(agent_id)

    if not agente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    return AgentRead.model_validate(agente)


@router.put("/agents/{agent_id:int}", response_model=AgentRead)
async def actualizar_agente(
    agent_id: int,
    datos: AgentUpdate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Update agent fields (name, hostname).

    Only updates the fields sent. At least one is required.
    """
    service = AgentService(session)
    try:
        agente = await service.actualizar_agente(
            agent_id,
            name=datos.name,
            hostname=datos.hostname,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    if not agente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    return AgentRead.model_validate(agente)


@router.delete("/agents/{agent_id:int}", response_model=dict)
async def eliminar_agente(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Permanently delete an agent by its ID."""
    service = AgentService(session)
    eliminado = await service.eliminar_agente(agent_id)

    if not eliminado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    return {"mensaje": f"Agent {agent_id} deleted"}


@router.post("/agents/desactivar-inactivos", response_model=dict)
async def desactivar_inactivos_endpoint(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Deactivate agents whose heartbeat has expired.

    Looks up active agents whose last_seen is before
    (now - heartbeat_timeout_minutes) and marks them as inactive.
    """
    service = AgentService(session)
    desactivados = await service.desactivar_inactivos()
    return {"desactivados": desactivados}
