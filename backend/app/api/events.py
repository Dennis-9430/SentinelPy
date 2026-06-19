"""Endpoints de la API para eventos de seguridad.

Permite ingestar eventos (desde colectores o API) y consultarlos.
Los colectores también pueden enviar eventos directamente por este canal.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session

# Router con prefijo /api/events — todas las rutas de eventos cuelgan de acá
router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
async def listar_eventos(session: AsyncSession = Depends(get_session)):
    """Lista los eventos más recientes (con paginación).

    Endpoint principal del dashboard. Devuelve eventos ordenados
    por timestamp descendente. TODO: implementar paginación y filtros.
    """
    return {"events": [], "total": 0}
