"""Statistics and CSV export endpoints.

Moved from main.py to a dedicated router to keep main.py clean.
"""

import csv
import io
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.alert import Alert
from app.models.event import NormalizedEvent
from app.schemas.common import AlertStatsResponse, EventStatsResponse

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/events", response_model=EventStatsResponse)
async def stats_eventos(
    horas: int = 24,
    session: AsyncSession = Depends(get_session),
):
    """Event statistics for dashboard charts.

    Returns:
        timeline: Events per hour in the last N hours.
        por_severidad: Event count grouped by severity.
    """
    ahora = datetime.now(UTC)
    desde = ahora - timedelta(hours=horas)

    # ── Timeline: events per hour ──────────────────────────────────
    timeline_raw = await session.execute(
        select(
            func.date_trunc("hour", NormalizedEvent.event_timestamp).label("hora"),
            func.count(NormalizedEvent.id).label("total"),
        )
        .where(NormalizedEvent.event_timestamp >= desde)
        .group_by("hora")
        .order_by("hora")
    )
    timeline = [
        {"hora": row.hora.isoformat(), "total": row.total} for row in timeline_raw
    ]

    # ── By severity ────────────────────────────────────────────────
    sev_raw = await session.execute(
        select(
            NormalizedEvent.severity,
            func.count(NormalizedEvent.id).label("total"),
        ).group_by(NormalizedEvent.severity)
    )
    por_severidad = {row.severity or "unknown": row.total for row in sev_raw}

    return EventStatsResponse(timeline=timeline, por_severidad=por_severidad)


@router.get("/alerts", response_model=AlertStatsResponse)
async def stats_alertas(
    session: AsyncSession = Depends(get_session),
):
    """Alert statistics for dashboard charts.

    Returns:
        por_severidad: Alert count grouped by severity.
        por_estado: Alert count grouped by status.
    """
    # ── By severity ────────────────────────────────────────────────
    sev_raw = await session.execute(
        select(
            Alert.severity,
            func.count(Alert.id).label("total"),
        ).group_by(Alert.severity)
    )
    por_severidad = {row.severity or "unknown": row.total for row in sev_raw}

    # ── By status ───────────────────────────────────────────────────
    est_raw = await session.execute(
        select(
            Alert.status,
            func.count(Alert.id).label("total"),
        ).group_by(Alert.status)
    )
    por_estado = {row.status or "unknown": row.total for row in est_raw}

    return AlertStatsResponse(por_severidad=por_severidad, por_estado=por_estado)


@router.get("/alerts/exportar")
async def exportar_alertas_csv(
    estado: str | None = None,
    severidad: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Export alerts to CSV with the current filters."""
    from app.services.alert_service import AlertService

    service = AlertService(session)
    alertas, _ = await service.listar_alertas(
        limite=10000, estado=estado, severidad=severidad
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "title",
            "severity",
            "status",
            "events",
            "created",
            "resolved",
            "description",
        ]
    )

    for a in alertas:
        writer.writerow(
            [
                str(a.id),
                a.title,
                a.severity,
                a.status,
                a.event_count,
                a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else "",
                a.resolved_at.strftime("%Y-%m-%d %H:%M:%S") if a.resolved_at else "",
                a.description or "",
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=alerts.csv",
        },
    )
