"""Event service: CRUD operations over normalized events.

Separates the data access logic from the API endpoints,
following the service layer pattern.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import NormalizedEvent

logger = logging.getLogger(__name__)


class EventService:
    """Service for creating and querying events in the database."""

    def __init__(self, session: AsyncSession):
        """
        Args:
            session: Async SQLAlchemy session.
        """
        self.session = session

    async def crear_evento(self, datos: dict) -> NormalizedEvent:
        """Create a new normalized event in the database.

        Receives a dictionary with the event fields (already parsed)
        and persists it to PostgreSQL.

        Args:
            datos: Dictionary with the normalized event fields.

        Returns:
            The created NormalizedEvent instance.
        """
        evento = NormalizedEvent(**datos)
        self.session.add(evento)
        await self.session.commit()
        await self.session.refresh(evento)
        logger.debug("Event created: %s - %s", evento.id, evento.event_type)
        return evento

    async def listar_eventos(
        self,
        limite: int = 50,
        desde: int = 0,
        tipo: str | None = None,
        severidad: str | None = None,
    ) -> tuple[list[NormalizedEvent], int]:
        """List events with pagination and optional filters.

        Args:
            limite: Maximum number of events to return.
            desde: Offset for pagination.
            tipo: Filter by event type (optional).
            severidad: Filter by severity (optional).

        Returns:
            Tuple (list of events, total events without pagination).
        """
        # Build base query
        query = select(NormalizedEvent).order_by(NormalizedEvent.event_timestamp.desc())
        count_query = select(func.count(NormalizedEvent.id))

        # Apply filters
        if tipo:
            query = query.where(NormalizedEvent.event_type == tipo)
            count_query = count_query.where(NormalizedEvent.event_type == tipo)
        if severidad:
            query = query.where(NormalizedEvent.severity == severidad)
            count_query = count_query.where(NormalizedEvent.severity == severidad)

        # Run count
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Run query with pagination
        result = await self.session.execute(query.offset(desde).limit(limite))
        eventos = list(result.scalars().all())

        return eventos, total

    async def obtener_estadisticas(self) -> dict:
        """Get basic event statistics.

        Returns:
            Dict with total event count, by severity, and by type.
        """
        # Total events
        total_result = await self.session.execute(
            select(func.count(NormalizedEvent.id))
        )
        total = total_result.scalar() or 0

        # Events in the last hour
        hace_una_hora = datetime.now(UTC) - timedelta(hours=1)
        recientes_result = await self.session.execute(
            select(func.count(NormalizedEvent.id)).where(
                NormalizedEvent.created_at >= hace_una_hora
            )
        )
        recientes = recientes_result.scalar() or 0

        return {
            "total_eventos": total,
            "eventos_ultima_hora": recientes,
        }
