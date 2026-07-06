"""Endpoints para agentes remotos: ingesta de eventos v2 y heartbeat.

Los agentes remotos se autentican via Bearer token (API key)
y pueden enviar batches de eventos normalizados a través de
POST /api/v2/events, así como reportar su estado mediante
POST /api/v2/agent/heartbeat.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import require_agent
from app.database import get_session
from app.models.agent import Agent
from app.services.pipeline import Pipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"], prefix="")

# ── Schemas específicos de agente ──────────────────────────────────────────


class AgentEventItem(BaseModel):
    """Un evento individual dentro del batch enviado por un agente.

    El agente puede enviar campos normalizados; el servidor completa
    los valores por defecto (collector_type, source, event_timestamp).
    """

    model_config = {"extra": "ignore"}

    source_ip: str | None = None
    destination_ip: str | None = None
    source_port: int | None = None
    destination_port: int | None = None
    protocol: str | None = None
    user_name: str | None = None
    process_name: str | None = None
    file_path: str | None = None
    raw_log: str | None = None
    event_type: str | None = None
    severity: str | None = None
    message: str | None = None
    event_timestamp: datetime | None = None
    source: str | None = None


class AgentEventBatch(BaseModel):
    """Batch de eventos enviado por un agente remoto.

    Máximo 100 eventos por request.
    """

    events: list[AgentEventItem]


class AgentHeartbeat(BaseModel):
    """Payload de heartbeat enviado por un agente."""

    hostname: str
    os: str
    agent_version: str


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.post("/api/v2/events", response_model=dict, status_code=201)
async def ingestar_eventos_batch(
    batch: AgentEventBatch,
    request: Request,
    agent: Agent = Depends(require_agent),
):
    """Ingesta un batch de eventos desde un agente remoto autenticado.

    Cada evento pasa por el pipeline completo (persistencia + engine).
    Si el procesamiento de un evento falla, se cuenta como failed
    pero se continúa con el resto del batch.

    Args:
        batch: Lista de hasta 100 eventos.
        request: Request de FastAPI para acceder a app.state.pipeline.
        agent: Agente autenticado via require_agent.

    Returns:
        Dict con processed, failed, event_ids.
    """
    if not batch.events:
        raise HTTPException(status_code=400, detail="Batch vacío")

    if len(batch.events) > 100:
        raise HTTPException(
            status_code=400,
            detail="Máximo 100 eventos por batch",
        )

    # Validar campos requeridos en cada evento
    for i, ev in enumerate(batch.events):
        if not ev.event_type or not ev.severity or not ev.message:
            raise HTTPException(
                status_code=400,
                detail=f"Evento {i}: faltan campos requeridos "
                       f"(event_type, severity, message)",
            )

    pipeline: Pipeline | None = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="Pipeline no disponible",
        )

    processed = 0
    failed = 0
    event_ids: list[str] = []

    ahora = datetime.now(timezone.utc)

    for ev in batch.events:
        evento_dict = ev.model_dump(exclude_none=True)

        # Forzar collector_type
        evento_dict["collector_type"] = "agent"

        # Usar hostname del agente como source si el evento no provee uno
        if not evento_dict.get("source"):
            evento_dict["source"] = agent.hostname

        # Timestamp por defecto
        if not evento_dict.get("event_timestamp"):
            evento_dict["event_timestamp"] = ahora

        # Mapear message → description
        evento_dict["description"] = evento_dict.pop("message")

        try:
            evento = await pipeline.process_from_dict(evento_dict)
            if evento:
                processed += 1
                event_ids.append(str(evento.id))
            else:
                failed += 1
        except Exception as e:
            logger.warning("Error procesando evento en batch: %s", e, exc_info=True)
            failed += 1

    return {
        "processed": processed,
        "failed": failed,
        "event_ids": event_ids,
    }


@router.post("/api/v2/agent/heartbeat", response_model=dict)
async def heartbeat(
    payload: AgentHeartbeat,
    request: Request,
    agent: Agent = Depends(require_agent),
    session: AsyncSession = Depends(get_session),
):
    """Recibe un heartbeat de un agente remoto.

    Actualiza last_seen del agente y retorna el timestamp del servidor.

    Args:
        payload: Datos del heartbeat (hostname, os, agent_version).
        request: Request de FastAPI.
        agent: Agente autenticado via require_agent.
        session: Sesión asíncrona de SQLAlchemy.

    Returns:
        Dict con status=ok y server_time en ISO 8601.
    """
    ahora = datetime.now(timezone.utc)
    agent.last_seen = ahora
    await session.commit()

    logger.debug(
        "Heartbeat recibido de %s (id=%d, hostname=%s)",
        agent.name, agent.id, payload.hostname,
    )

    return {
        "status": "ok",
        "server_time": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
