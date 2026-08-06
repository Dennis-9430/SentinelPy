"""Endpoints for remote agents: v2 event ingestion and heartbeat.

Remote agents authenticate via Bearer token (API key)
and can send normalized event batches through
POST /api/v2/events, as well as report their status via
POST /api/v2/agent/heartbeat.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_agent
from app.database import get_session
from app.models.agent import Agent
from app.ratelimit import RateLimiter
from app.services.pipeline import Pipeline

# ── Shared rate limiter ───────────────────────────────────────────────

rate_limiter = RateLimiter()

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"], prefix="")

# ── Agent-specific schemas ──────────────────────────────────────────


class AgentEventItem(BaseModel):
    """A single event within the batch sent by an agent.

    The agent can send normalized fields; the server fills in
    the default values (collector_type, source, event_timestamp).
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
    """Batch of events sent by a remote agent.

    Maximum 100 events per request.
    """

    events: list[AgentEventItem]


class AgentHeartbeat(BaseModel):
    """Heartbeat payload sent by an agent."""

    hostname: str
    os: str
    agent_version: str


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.post("/api/v2/events", response_model=dict, status_code=201)
async def ingestar_eventos_batch(
    batch: AgentEventBatch,
    request: Request,
    agent: Agent = Depends(rate_limiter),
):
    """Ingest a batch of events from an authenticated remote agent.

    Each event goes through the full pipeline (persistence + engine).
    If processing an event fails, it is counted as failed
    but the rest of the batch continues.

    Args:
        batch: List of up to 100 events.
        request: FastAPI request used to access app.state.pipeline.
        agent: Agent authenticated via require_agent.

    Returns:
        Dict with processed, failed, event_ids.
    """
    if not batch.events:
        raise HTTPException(status_code=400, detail="Empty batch")

    if len(batch.events) > 100:
        raise HTTPException(
            status_code=400,
            detail="Maximum 100 events per batch",
        )

    # Validate required fields on each event
    for i, ev in enumerate(batch.events):
        if not ev.event_type or not ev.severity or not ev.message:
            raise HTTPException(
                status_code=400,
                detail=f"Event {i}: missing required fields "
                f"(event_type, severity, message)",
            )

    pipeline: Pipeline | None = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="Pipeline unavailable",
        )

    processed = 0
    failed = 0
    event_ids: list[str] = []

    ahora = datetime.now(UTC)

    for ev in batch.events:
        evento_dict = ev.model_dump(exclude_none=True)

        # Force collector_type
        evento_dict["collector_type"] = "agent"

        # Use the agent hostname as source if the event does not provide one
        if not evento_dict.get("source"):
            evento_dict["source"] = agent.hostname

        # Default timestamp
        if not evento_dict.get("event_timestamp"):
            evento_dict["event_timestamp"] = ahora

        # Map message → description
        evento_dict["description"] = evento_dict.pop("message")

        try:
            evento = await pipeline.process_from_dict(evento_dict)
            if evento:
                processed += 1
                event_ids.append(str(evento.id))
            else:
                failed += 1
        except Exception as e:
            logger.warning("Error processing event in batch: %s", e, exc_info=True)
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
    """Receive a heartbeat from a remote agent.

    Updates the agent's last_seen and returns the server timestamp.

    Args:
        payload: Heartbeat data (hostname, os, agent_version).
        request: FastAPI request.
        agent: Agent authenticated via require_agent.
        session: Async SQLAlchemy session.

    Returns:
        Dict with status=ok and server_time in ISO 8601.
    """
    ahora = datetime.now(UTC)
    agent.last_seen = ahora
    await session.commit()

    logger.debug(
        "Heartbeat received from %s (id=%d, hostname=%s)",
        agent.name,
        agent.id,
        payload.hostname,
    )

    return {
        "status": "ok",
        "server_time": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
