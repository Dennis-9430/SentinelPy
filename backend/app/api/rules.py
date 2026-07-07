"""Endpoints de la API para reglas de detección.

CRUD completo de reglas estilo Sigma. Las reglas activas se cargan
en el motor de correlación al iniciar la aplicación.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_session
from app.models.user import User
from app.schemas.rule import RuleCreate
from app.services.rule_service import RuleService

# Router con prefijo /api/rules
router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("", response_model=dict)
async def listar_reglas(
    limite: int = Query(100, ge=1, le=500, description="Cantidad máxima de reglas"),
    desde: int = Query(0, ge=0, description="Offset para paginación"),
    estado: str | None = Query(
        None, description="Filtrar por estado: active, disabled, test"
    ),
    severidad: str | None = Query(None, description="Filtrar por severidad"),
    session: AsyncSession = Depends(get_session),
):
    """Devuelve todas las reglas de detección con paginación y filtros."""
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
    """Obtiene una regla por su ID."""
    service = RuleService(session)
    regla = await service.obtener_regla(regla_id)

    if not regla:
        raise HTTPException(status_code=404, detail="Regla no encontrada")

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
    """Crea una nueva regla de detección (solo admin).

    La regla se guarda en la base de datos y, si está activa,
    se cargará en el motor de correlación en el próximo ciclo.
    """
    service = RuleService(session)
    regla = await service.crear_regla(datos.model_dump())

    # Intentar recargar reglas en el engine (si está disponible)
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
    """Actualiza una regla existente (solo admin)."""
    service = RuleService(session)
    regla = await service.actualizar_regla(
        regla_id, datos.model_dump(exclude_unset=True)
    )

    if not regla:
        raise HTTPException(status_code=404, detail="Regla no encontrada")

    # Recargar reglas en el engine
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
    """Elimina una regla por su ID (solo admin)."""
    service = RuleService(session)
    eliminado = await service.eliminar_regla(regla_id)

    if not eliminado:
        raise HTTPException(status_code=404, detail="Regla no encontrada")

    # Recargar reglas en el engine
    await _recargar_engine(session)


def _toggle_status(current_status: str) -> str:
    """Retorna el estado opuesto para toggle active/disabled.

    Args:
        current_status: Estado actual ('active' o 'disabled').

    Returns:
        'disabled' si current_status es 'active', 'active' en caso contrario.
    """
    return "disabled" if current_status == "active" else "active"


@router.patch("/{regla_id}/toggle", response_model=dict)
async def toggle_regla(
    regla_id: str,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Activa/desactiva una regla (solo admin). Retorna JSON.

    El estado cambia entre active y disabled. Después del toggle
    recarga el motor de correlación para aplicar el cambio.
    """
    service = RuleService(session)
    regla = await service.obtener_regla(regla_id)

    if not regla:
        raise HTTPException(status_code=404, detail="Regla no encontrada")

    nuevo_estado = _toggle_status(regla.status)
    await service.actualizar_regla(regla_id, {"status": nuevo_estado})

    # Recargar engine para aplicar el cambio
    await _recargar_engine(session)

    return {"status": nuevo_estado}


async def _recargar_engine(session: AsyncSession):
    """Recarga las reglas activas en el motor de correlación.

    Se llama después de crear, actualizar o eliminar una regla
    para mantener el engine sincronizado sin reiniciar la app.
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

        logging.getLogger(__name__).warning("No se pudo recargar engine: %s", e)
