"""Endpoints de la API para análisis de eventos.

Provee acceso a anomalías detectadas (z-scores) y scores de riesgo
por entidad. Los datos se generan de forma asíncrona por el
AnalysisService en el pipeline de procesamiento.
"""

import logging

from fastapi import APIRouter, Query, Request

logger = logging.getLogger(__name__)

# Router con prefijo /api/analysis
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/anomalies", response_model=dict)
async def listar_anomalias(
    request: Request,
    limite: int = Query(50, ge=1, le=500, description="Cantidad máxima"),
    desde: int = Query(0, ge=0, description="Offset para paginación"),
):
    """Lista eventos con anomalías detectadas (analysis_data != null).

    Retorna eventos que tienen z-scores calculados por el
    AnalysisService. Los resultados se ordenan por timestamp descendente.
    """
    service = getattr(request.app.state, "analysis_service", None)
    if service is None:
        return {"anomalies": [], "total": 0}

    try:
        anomalias, total = await service.get_anomalies(
            limit=limite, offset=desde
        )
        return {"anomalies": anomalias, "total": total}
    except Exception as e:
        logger.error("Error obteniendo anomalías: %s", e, exc_info=True)
        return {"anomalies": [], "total": 0}


@router.get("/risks", response_model=dict)
async def listar_riesgos(
    request: Request,
    limite: int = Query(50, ge=1, le=500, description="Cantidad máxima"),
    desde: int = Query(0, ge=0, description="Offset para paginación"),
):
    """Lista scores de riesgo por entidad.

    Retorna el riesgo actual (con decaimiento aplicado) para cada
    entidad rastreada (IPs, usuarios, fuentes).
    """
    service = getattr(request.app.state, "analysis_service", None)
    if service is None:
        return {"risks": [], "total": 0}

    try:
        risks, total = await service.get_risks(limit=limite, offset=desde)
        return {"risks": risks, "total": total}
    except Exception as e:
        logger.error("Error obteniendo riesgos: %s", e, exc_info=True)
        return {"risks": [], "total": 0}
