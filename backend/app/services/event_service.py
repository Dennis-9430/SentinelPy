"""Servicio de eventos: operaciones CRUD sobre eventos normalizados.

Separa la lógica de acceso a datos de los endpoints de la API,
siguiendo el patrón de capa de servicio.
"""

import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.event import NormalizedEvent

logger = logging.getLogger(__name__)


class EventService:
    """Servicio para crear y consultar eventos en la base de datos."""

    def __init__(self, session: AsyncSession):
        """
        Argumentos:
            session: Sesión asíncrona de SQLAlchemy.
        """
        self.session = session

    async def crear_evento(self, datos: dict) -> NormalizedEvent:
        """Crea un nuevo evento normalizado en la base de datos.

        Recibe un diccionario con los campos del evento (ya parseado)
        y lo persiste en PostgreSQL.

        Argumentos:
            datos: Diccionario con los campos del evento normalizado.

        Retorna:
            La instancia de NormalizedEvent creada.
        """
        evento = NormalizedEvent(**datos)
        self.session.add(evento)
        await self.session.commit()
        await self.session.refresh(evento)
        logger.debug("Evento creado: %s - %s", evento.id, evento.event_type)
        return evento

    async def listar_eventos(
        self,
        limite: int = 50,
        desde: int = 0,
        tipo: str | None = None,
        severidad: str | None = None,
    ) -> tuple[list[NormalizedEvent], int]:
        """Lista eventos con paginación y filtros opcionales.

        Argumentos:
            limite: Cantidad máxima de eventos a retornar.
            desde: Offset para paginación.
            tipo: Filtrar por tipo de evento (opcional).
            severidad: Filtrar por severidad (opcional).

        Retorna:
            Tupla (lista de eventos, total de eventos sin paginación).
        """
        # Construir query base
        query = select(NormalizedEvent).order_by(NormalizedEvent.event_timestamp.desc())
        count_query = select(func.count(NormalizedEvent.id))

        # Aplicar filtros
        if tipo:
            query = query.where(NormalizedEvent.event_type == tipo)
            count_query = count_query.where(NormalizedEvent.event_type == tipo)
        if severidad:
            query = query.where(NormalizedEvent.severity == severidad)
            count_query = count_query.where(NormalizedEvent.severity == severidad)

        # Ejecutar count
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Ejecutar query con paginación
        result = await self.session.execute(
            query.offset(desde).limit(limite)
        )
        eventos = list(result.scalars().all())

        return eventos, total

    async def obtener_estadisticas(self) -> dict:
        """Obtiene estadísticas básicas de eventos.

        Retorna:
            Dict con conteo de eventos totales, por severidad, y por tipo.
        """
        # Total de eventos
        total_result = await self.session.execute(
            select(func.count(NormalizedEvent.id))
        )
        total = total_result.scalar() or 0

        # Eventos en la última hora
        hace_una_hora = datetime.now(timezone.utc) - timedelta(hours=1)
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
