"""Endpoints de la API para alertas de seguridad.

Listado, filtrado, y actualización del ciclo de vida de alertas.
Las alertas se generan automáticamente por el motor de correlación.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas.alert import AlertRead, AlertUpdateStatus
from app.services.alert_service import AlertService

# Router con prefijo /api/alerts
router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=dict)
async def listar_alertas(
    limite: int = Query(50, ge=1, le=500, description="Cantidad máxima de alertas"),
    desde: int = Query(0, ge=0, description="Offset para paginación"),
    estado: str | None = Query(None, description="Filtrar por estado: open, acknowledged, investigating, resolved, false_positive"),
    severidad: str | None = Query(None, description="Filtrar por severidad"),
    session: AsyncSession = Depends(get_session),
):
    """Lista las alertas con filtros y paginación."""
    service = AlertService(session)
    alertas, total = await service.listar_alertas(
        limite=limite, desde=desde, estado=estado, severidad=severidad
    )

    return {
        "alertas": [
            {
                "id": str(a.id),
                "rule_id": str(a.rule_id),
                "title": a.title,
                "severity": a.severity,
                "description": a.description[:200] if a.description else "",
                "status": a.status,
                "event_count": a.event_count,
                "first_event_at": a.first_event_at.isoformat() if a.first_event_at else None,
                "last_event_at": a.last_event_at.isoformat() if a.last_event_at else None,
                "created_at": a.created_at.isoformat(),
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
            }
            for a in alertas
        ],
        "total": total,
    }


@router.get("/{alerta_id}", response_model=dict)
async def obtener_alerta(
    alerta_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Obtiene una alerta por su ID con todos los detalles."""
    service = AlertService(session)
    alerta = await service.obtener_alerta(alerta_id)

    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")

    return {
        "id": str(alerta.id),
        "rule_id": str(alerta.rule_id),
        "title": alerta.title,
        "severity": alerta.severity,
        "description": alerta.description,
        "status": alerta.status,
        "event_count": alerta.event_count,
        "first_event_at": alerta.first_event_at.isoformat() if alerta.first_event_at else None,
        "last_event_at": alerta.last_event_at.isoformat() if alerta.last_event_at else None,
        "created_at": alerta.created_at.isoformat(),
        "updated_at": alerta.updated_at.isoformat(),
        "resolved_at": alerta.resolved_at.isoformat() if alerta.resolved_at else None,
        "resolution_notes": alerta.resolution_notes,
    }


@router.patch("/{alerta_id}/estado", response_model=dict)
async def actualizar_estado_alerta(
    alerta_id: str,
    datos: dict,  # {"status": "investigating", "resolution_notes": "..."}
    session: AsyncSession = Depends(get_session),
):
    """Actualiza el estado de una alerta (ciclo de vida).

    Estados posibles: open → acknowledged → investigating → resolved | false_positive
    """
    nuevo_estado = datos.get("status")
    notas = datos.get("resolution_notes")

    if not nuevo_estado:
        raise HTTPException(status_code=400, detail="El campo 'status' es requerido")

    estados_validos = {"open", "acknowledged", "investigating", "resolved", "false_positive"}
    if nuevo_estado not in estados_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Estado inválido. Válidos: {', '.join(sorted(estados_validos))}",
        )

    service = AlertService(session)
    alerta = await service.actualizar_estado(alerta_id, nuevo_estado, notas)

    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")

    return {
        "id": str(alerta.id),
        "status": alerta.status,
        "resolved_at": alerta.resolved_at.isoformat() if alerta.resolved_at else None,
        "updated_at": alerta.updated_at.isoformat(),
    }


@router.get("/estadisticas", response_model=dict)
async def obtener_estadisticas_alertas(
    session: AsyncSession = Depends(get_session),
):
    """Obtiene estadísticas de alertas (totales, abiertas, resueltas)."""
    service = AlertService(session)
    return await service.obtener_estadisticas()
