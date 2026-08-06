"""API endpoints for detection rules.

Full Sigma-style rule CRUD. Active rules are loaded
into the correlation engine at application startup.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_session
from app.models.user import User
from app.schemas.rule import RuleCreate
from app.services.rule_service import RuleService

# Router with /api/rules prefix
router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_model=dict)
async def listar_reglas(
    limite: int = Query(100, ge=1, le=500, description="Maximum number of rules"),
    desde: int = Query(0, ge=0, description="Offset for pagination"),
    estado: str | None = Query(
        None, description="Filter by status: active, disabled, test"
    ),
    severidad: str | None = Query(None, description="Filter by severity"),
    session: AsyncSession = Depends(get_session),
):
    """Return all detection rules with pagination and filters."""
    service = RuleService(session)
    reglas, total = await service.listar_reglas(
        limite=limite, desde=desde, estado=estado, severidad=severidad
    )

    return {
        "reglas": [
            {
                "id": str(r.id),
                "title": r.title,
                "description": r.description[:200] if r.description else "",
                "author": r.author,
                "severity": r.severity,
                "status": r.status,
                "conditions": r.conditions,
                "correlation_window": r.correlation_window,
                "alert_title": r.alert_title,
                "alert_severity": r.alert_severity,
                "tags": r.tags,
                "created_at": r.created_at.isoformat(),
            }
            for r in reglas
        ],
        "total": total,
    }


@router.get("/{regla_id}", response_model=dict)
async def obtener_regla(
    regla_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get a rule by its ID."""
    service = RuleService(session)
    regla = await service.obtener_regla(regla_id)

    if not regla:
        raise HTTPException(status_code=404, detail="Rule not found")

    return {
        "id": str(regla.id),
        "title": regla.title,
        "description": regla.description,
        "author": regla.author,
        "severity": regla.severity,
        "status": regla.status,
        "conditions": regla.conditions,
        "correlation_window": regla.correlation_window,
        "alert_title": regla.alert_title,
        "alert_severity": regla.alert_severity,
        "tags": regla.tags,
        "references": regla.references,
        "false_positives": regla.false_positives,
        "created_at": regla.created_at.isoformat(),
        "updated_at": regla.updated_at.isoformat(),
    }


@router.post("", response_model=dict, status_code=201)
async def crear_regla(
    datos: RuleCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Create a new detection rule (admin only).

    The rule is saved to the database and, if active,
    will be loaded into the correlation engine on the next cycle.
    """
    service = RuleService(session)
    regla = await service.crear_regla(datos.model_dump())

    # Try to reload rules into the engine (if available)
    await _recargar_engine(session)

    return {
        "id": str(regla.id),
        "title": regla.title,
        "severity": regla.severity,
        "status": regla.status,
        "created_at": regla.created_at.isoformat(),
    }


@router.put("/{regla_id}", response_model=dict)
async def actualizar_regla(
    regla_id: str,
    datos: RuleCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Update an existing rule (admin only)."""
    service = RuleService(session)
    regla = await service.actualizar_regla(
        regla_id, datos.model_dump(exclude_unset=True)
    )

    if not regla:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Reload rules into the engine
    await _recargar_engine(session)

    return {
        "id": str(regla.id),
        "title": regla.title,
        "status": regla.status,
        "updated_at": regla.updated_at.isoformat(),
    }


@router.delete("/{regla_id}", status_code=204)
async def eliminar_regla(
    regla_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Delete a rule by its ID (admin only)."""
    service = RuleService(session)
    eliminado = await service.eliminar_regla(regla_id)

    if not eliminado:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Reload rules into the engine
    await _recargar_engine(session)


def _toggle_status(current_status: str) -> str:
    """Return the opposite status for active/disabled toggling.

    Args:
        current_status: Current status ('active' or 'disabled').

    Returns:
        'disabled' if current_status is 'active', 'active' otherwise.
    """
    return "disabled" if current_status == "active" else "active"


@router.patch("/{regla_id}/toggle", response_model=dict)
async def toggle_regla(
    regla_id: str,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Enable/disable a rule (admin only). Returns JSON.

    The status toggles between active and disabled. After the toggle
    it reloads the correlation engine to apply the change.
    """
    service = RuleService(session)
    regla = await service.obtener_regla(regla_id)

    if not regla:
        raise HTTPException(status_code=404, detail="Rule not found")

    nuevo_estado = _toggle_status(regla.status)
    await service.actualizar_regla(regla_id, {"status": nuevo_estado})

    # Reload engine to apply the change
    await _recargar_engine(session)

    return {"status": nuevo_estado}


async def _recargar_engine(session: AsyncSession):
    """Reload active rules into the correlation engine.

    Called after creating, updating or deleting a rule to keep
    the engine synchronized without restarting the app.
    """
    try:
        from app.main import app as app_instance

        engine = getattr(app_instance.state, "engine", None)
        if engine:
            service = RuleService(session)
            reglas = await service.cargar_reglas_activas()
            engine.cargar_reglas(reglas)
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("Could not reload engine: %s", e)
