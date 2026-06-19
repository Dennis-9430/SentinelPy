"""Endpoints de la API para alertas de seguridad.

Listado, filtrado, y actualización del ciclo de vida de alertas.
Las alertas se generan automáticamente por el motor de correlación.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session

# Router con prefijo /api/alerts
router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def listar_alertas(session: AsyncSession = Depends(get_session)):
    """Lista las alertas con filtro opcional por estado.

    Estados posibles: open, acknowledged, investigating, resolved, false_positive.
    TODO: implementar paginación, filtros por severidad y rango de fechas.
    """
    return {"alerts": [], "total": 0}
