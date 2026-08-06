"""API endpoints for security events.

Allows ingesting events (from collectors or external API) and querying them.
Internal collectors can also send events directly through this channel.
"""

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.event import EventCreate
from app.services.event_service import EventService
from app.services.pipeline import Pipeline

logger = logging.getLogger(__name__)

# Router with /api/events prefix — all event routes hang from here
router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=dict)
async def listar_eventos(
    limite: int = Query(50, ge=1, le=500, description="Maximum number of events"),
    desde: int = Query(0, ge=0, description="Offset for pagination"),
    tipo: str | None = Query(None, description="Filter by event type"),
    severidad: str | None = Query(None, description="Filter by severity"),
    session: AsyncSession = Depends(get_session),
):
    """List the most recent events with pagination and filters.

    Returns:
        Dict with list of events and total (without pagination).
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
    """Ingest a new event from the REST API.

    Useful for integrations with external systems that want to send
    events directly to SentinelPy without going through the syslog collector.
    After persisting the event, it sends it to the pipeline for evaluation
    by the correlation engine (Engine.evaluate()).

    Args:
        datos: Normalized event in JSON format (see EventCreate schema).
        request: FastAPI request used to access app.state.

    Returns:
        Dict with the data of the created event.
    """
    evento_dict = datos.model_dump()

    # Try the full pipeline (persists + evaluates engine)
    pipeline: Pipeline | None = getattr(request.app.state, "pipeline", None)
    if pipeline is not None:
        try:
            evento = await pipeline.process_from_dict(
                evento_dict, collector_type="rest"
            )
        except Exception as e:
            logger.warning(
                "Pipeline.process_from_dict failed, saving event without engine: %s",
                e,
                exc_info=True,
            )
            evento = None
    else:
        evento = None

    # Fallback: at least save the event in DB
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
    """Get event statistics (totals, recent, etc.).

    Useful for the dashboard and overall system monitoring.
    """
    service = EventService(session)
    stats = await service.obtener_estadisticas()
    return stats
