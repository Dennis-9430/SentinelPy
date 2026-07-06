"""Endpoints de la API para eventos de seguridad.

Permite ingestar eventos (desde colectores o API externa) y consultarlos.
Los colectores internos también pueden enviar eventos directamente por este canal.
"""

import logging
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas.event import EventCreate, EventRead
from app.services.event_service import EventService
from app.services.pipeline import Pipeline

logger = logging.getLogger(__name__)

# Router con prefijo /api/events — todas las rutas de eventos cuelgan de acá
router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=dict)
async def listar_eventos(
    limite: int = Query(50, ge=1, le=500, description="Cantidad máxima de eventos"),
    desde: int = Query(0, ge=0, description="Offset para paginación"),
    tipo: str | None = Query(None, description="Filtrar por tipo de evento"),
    severidad: str | None = Query(None, description="Filtrar por severidad"),
    session: AsyncSession = Depends(get_session),
):
    """Lista los eventos más recientes con paginación y filtros.

    Returns:
        Dict con lista de eventos y total (sin paginación).
    """
    service = EventService(session)
    eventos, total = await service.listar_eventos(
        limite=limite, desde=desde, tipo=tipo, severidad=severidad
    )

    return {
        "eventos": [
            {
                "id": str(e.id),
                "source": e.source,
                "collector_type": e.collector_type,
                "event_timestamp": e.event_timestamp.isoformat(),
                "event_type": e.event_type,
                "severity": e.severity,
                "description": e.description[:200] if e.description else "",
                "source_ip": e.source_ip,
                "destination_ip": e.destination_ip,
                "process_name": e.process_name,
                "user_name": e.user_name,
                "created_at": e.created_at.isoformat(),
            }
            for e in eventos
        ],
        "total": total,
    }


@router.post("", response_model=dict, status_code=201)
async def crear_evento(
    datos: EventCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Ingesta un nuevo evento desde la API REST.

    Útil para integraciones con sistemas externos que quieran enviar
    eventos directamente a SentinelPy sin pasar por el colector syslog.
    Tras persistir el evento, lo envía al pipeline para evaluación
    del motor de correlación (Engine.evaluate()).

    Args:
        datos: Evento normalizado en formato JSON (ver esquema EventCreate).
        request: Request de FastAPI para acceder a app.state.

    Returns:
        Dict con los datos del evento creado.
    """
    evento_dict = datos.model_dump()

    # Intentar pipeline completo (persiste + evalúa engine)
    pipeline: Pipeline | None = getattr(request.app.state, "pipeline", None)
    if pipeline is not None:
        try:
            evento = await pipeline.process_from_dict(
                evento_dict, collector_type="rest"
            )
        except Exception as e:
            logger.warning(
                "Pipeline.process_from_dict falló, guardando evento sin engine: %s",
                e, exc_info=True,
            )
            evento = None
    else:
        evento = None

    # Fallback: guardar al menos el evento en DB
    if evento is None:
        service = EventService(session)
        evento = await service.crear_evento(evento_dict)

    return {
        "id": str(evento.id),
        "event_type": evento.event_type,
        "severity": evento.severity,
        "source": evento.source,
        "event_timestamp": evento.event_timestamp.isoformat(),
        "created_at": evento.created_at.isoformat(),
    }


@router.get("/estadisticas")
async def obtener_estadisticas(session: AsyncSession = Depends(get_session)):
    """Obtiene estadísticas de eventos (totales, recientes, etc.).

    Útil para el dashboard y monitoreo general del sistema.
    """
    service = EventService(session)
    stats = await service.obtener_estadisticas()
    return stats
