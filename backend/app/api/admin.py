"""Endpoints de administración de agentes remotos (solo admin).

Permite listar, crear y desactivar agentes.
Todos los endpoints requieren rol admin autenticado.
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

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/agents", response_model=AgentList)
async def listar_agentes(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
    page: int = Query(1, ge=1, description="Número de página"),
    per_page: int = Query(10, ge=1, le=100, description="Agentes por página"),
):
    """Lista todos los agentes registrados con paginación (activos e inactivos).

    Solo accesible para administradores autenticados.
    Nunca expone api_key_hash ni api_key_raw.
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
    """Crea un nuevo agente remoto con API key generada automáticamente.

    La API key se genera con secrets.token_urlsafe(32) y se hashea
    con bcrypt antes de persistir. La key plaintext se retorna en
    api_key_raw UNA SOLA VEZ — no se puede recuperar después.
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
    """Desactiva un agente por su ID.

    Un agente desactivado no puede autenticarse ni enviar eventos.
    """
    service = AgentService(session)
    desactivado = await service.desactivar_agente(agent_id)

    if not desactivado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agente no encontrado",
        )

    return {"mensaje": f"Agente {agent_id} desactivado"}


@router.get("/agents/{agent_id:int}", response_model=AgentRead)
async def obtener_agente(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Obtiene un agente por su ID.

    Retorna todos los campos del agente sin exponer api_key_hash.
    """
    service = AgentService(session)
    agente = await service.obtener_por_id(agent_id)

    if not agente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agente no encontrado",
        )

    return AgentRead.model_validate(agente)


@router.put("/agents/{agent_id:int}", response_model=AgentRead)
async def actualizar_agente(
    agent_id: int,
    datos: AgentUpdate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Actualiza campos de un agente (name, hostname).

    Solo actualiza los campos enviados. Al menos uno es requerido.
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
            detail="Agente no encontrado",
        )

    return AgentRead.model_validate(agente)


@router.delete("/agents/{agent_id:int}", response_model=dict)
async def eliminar_agente(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Elimina un agente por su ID permanentemente."""
    service = AgentService(session)
    eliminado = await service.eliminar_agente(agent_id)

    if not eliminado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agente no encontrado",
        )

    return {"mensaje": f"Agente {agent_id} eliminado"}


@router.post("/agents/desactivar-inactivos", response_model=dict)
async def desactivar_inactivos_endpoint(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Desactiva agentes cuyo heartbeat ha expirado.

    Busca agents activos cuyo last_seen sea anterior a
    (ahora - heartbeat_timeout_minutes) y los marca como inactivos.
    """
    service = AgentService(session)
    desactivados = await service.desactivar_inactivos()
    return {"desactivados": desactivados}
