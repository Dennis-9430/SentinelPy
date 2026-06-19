"""Endpoints de la API para reglas de detección.

CRUD completo de reglas estilo Sigma. Las reglas activas se cargan
en el motor de correlación al iniciar la aplicación.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session

# Router con prefijo /api/rules
router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("")
async def listar_reglas(session: AsyncSession = Depends(get_session)):
    """Devuelve todas las reglas de detección.

    TODO: implementar filtros por estado (active/disabled/test)
    y búsqueda por texto en título/descripción.
    """
    return {"rules": [], "total": 0}
