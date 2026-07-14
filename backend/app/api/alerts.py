"""Endpoints de la API para alertas de seguridad.

Listado, filtrado, y actualización del ciclo de vida de alertas.
Las alertas se generan automáticamente por el motor de correlación.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_session
from app.models.user import User
from app.schemas.alert import (
    AlertGroupListResponse,
    AlertListItem,
    AlertListResponse,
    AlertRead,
    AlertUpdateResponse,
    AlertUpdateStatus,
)
from app.services.alert_service import AlertService

# Router con prefijo /alerts (bajo /api/v1 o /api)
router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
async def listar_alertas(
    limite: int = Query(50, ge=1, le=500, description="Cantidad máxima de alertas"),
    desde: int = Query(0, ge=0, description="Offset para paginación"),
    estado: str | None = Query(
        None,
        description="Filtrar por estado: open, acknowledged, investigating, resolved, false_positive",
    ),
    severidad: str | None = Query(None, description="Filtrar por severidad"),
    session: AsyncSession = Depends(get_session),
):
    """Lista las alertas con filtros y paginación."""
    service = AlertService(session)
    alertas, total = await service.listar_alertas(
        limite=limite, desde=desde, estado=estado, severidad=severidad
    )

    return AlertListResponse(
        alertas=[
            AlertListItem(
                id=str(a.id),
                rule_id=str(a.rule_id),
                title=a.title,
                severity=a.severity,
                description=a.description[:200] if a.description else "",
                status=a.status,
                event_count=a.event_count,
                first_event_at=a.first_event_at,
                last_event_at=a.last_event_at,
                created_at=a.created_at,
                resolved_at=a.resolved_at,
            )
            for a in alertas
        ],
        total=total,
    )


@router.get("/groups", response_model=AlertGroupListResponse)
async def listar_grupos_alertas(
    session: AsyncSession = Depends(get_session),
):
    """Lista alertas agrupadas por group_key."""
    from collections import defaultdict

    from sqlalchemy import select

    from app.models.alert import Alert
    from app.schemas.alert import AlertGroup, AlertGroupAlert

    result = await session.execute(
        select(Alert)
        .where(
            Alert.status.in_(["open", "acknowledged", "investigating"]),
            Alert.group_key.isnot(None),
        )
        .order_by(Alert.created_at.desc())
    )
    open_alerts = list(result.scalars().all())

    if not open_alerts:
        return AlertGroupListResponse(groups=[], total=0)

    groups_map: dict[str, list[Alert]] = defaultdict(list)
    for a in open_alerts:
        groups_map[a.group_key].append(a)

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

    groups = []
    for gk, alerts in groups_map.items():
        max_sev = min(
            (a.severity for a in alerts),
            key=lambda s: severity_order.get(s, 5),
        )
        risk = next((a.risk_score for a in alerts if a.risk_score is not None), None)

        groups.append(
            AlertGroup(
                group_key=gk,
                group_name=alerts[0].group_name or "",
                alert_count=len(alerts),
                max_severity=max_sev,
                risk_score=risk,
                alerts=[
                    AlertGroupAlert(
                        id=str(a.id),
                        rule_id=str(a.rule_id),
                        title=a.title,
                        severity=a.severity,
                        description=(a.description[:200] if a.description else ""),
                        status=a.status,
                        group_key=a.group_key,
                        group_name=a.group_name,
                        risk_score=a.risk_score,
                        event_count=a.event_count,
                        created_at=a.created_at,
                    )
                    for a in alerts
                ],
            )
        )

    return AlertGroupListResponse(groups=groups, total=len(groups))


@router.get("/{alerta_id}", response_model=AlertRead)
async def obtener_alerta(
    alerta_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Obtiene una alerta por su ID con todos los detalles."""
    service = AlertService(session)
    alerta = await service.obtener_alerta(alerta_id)

    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")

    return AlertRead.model_validate(alerta)


@router.patch("/{alerta_id}/estado", response_model=AlertUpdateResponse)
async def actualizar_estado_alerta(
    alerta_id: str,
    datos: AlertUpdateStatus,
    request: Request,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Actualiza el estado de una alerta (solo admin).

    Estados posibles: open → acknowledged → investigating → resolved | false_positive
    """
    estados_validos = {
        "open",
        "acknowledged",
        "investigating",
        "resolved",
        "false_positive",
    }
    if datos.status not in estados_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Estado inválido. Válidos: {', '.join(sorted(estados_validos))}",
        )

    service = AlertService(session)
    alerta = await service.actualizar_estado(
        alerta_id, datos.status, datos.resolution_notes
    )

    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")

    return AlertUpdateResponse(
        id=str(alerta.id),
        status=alerta.status,
        resolved_at=alerta.resolved_at,
        updated_at=alerta.updated_at,
    )


@router.get("/estadisticas")
async def obtener_estadisticas_alertas(
    session: AsyncSession = Depends(get_session),
):
    """Obtiene estadísticas de alertas (totales, abiertas, resueltas)."""
    service = AlertService(session)
    return await service.obtener_estadisticas()
