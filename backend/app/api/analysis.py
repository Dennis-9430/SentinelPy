"""API endpoints for event analysis.

Provides access to detected anomalies (z-scores) and risk scores
per entity. The data is generated asynchronously by the
AnalysisService in the processing pipeline.
"""

import logging

from fastapi import APIRouter, Query, Request

logger = logging.getLogger(__name__)

# Router with /api/analysis prefix
router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/anomalies", response_model=dict)
async def listar_anomalias(
    request: Request,
    limite: int = Query(50, ge=1, le=500, description="Maximum count"),
    desde: int = Query(0, ge=0, description="Offset for pagination"),
):
    """List events with detected anomalies (analysis_data != null).

    Returns events that have z-scores computed by the
    AnalysisService. Results are ordered by descending timestamp.
    """
    service = getattr(request.app.state, "analysis_service", None)
    if service is None:
        return {"anomalies": [], "total": 0}

    try:
        anomalias, total = await service.get_anomalies(limit=limite, offset=desde)
        return {"anomalies": anomalias, "total": total}
    except Exception as e:
        logger.error("Error getting anomalies: %s", e, exc_info=True)
        return {"anomalies": [], "total": 0}


@router.get("/risks", response_model=dict)
async def listar_riesgos(
    request: Request,
    limite: int = Query(50, ge=1, le=500, description="Maximum count"),
    desde: int = Query(0, ge=0, description="Offset for pagination"),
):
    """List risk scores per entity.

    Returns the current risk (with decay applied) for each
    tracked entity (IPs, users, sources).
    """
    service = getattr(request.app.state, "analysis_service", None)
    if service is None:
        return {"risks": [], "total": 0}

    try:
        risks, total = await service.get_risks(limit=limite, offset=desde)
        return {"risks": risks, "total": total}
    except Exception as e:
        logger.error("Error getting risks: %s", e, exc_info=True)
        return {"risks": [], "total": 0}
