"""Servicio de alertas: consulta y actualización del ciclo de vida.

Las alertas se generan automáticamente por el motor de correlación.
Este servicio solo permite consultarlas y actualizar su estado.
"""

import logging
from datetime import datetime, timezone
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.alert import Alert

logger = logging.getLogger(__name__)


class AlertService:
    """Servicio para consultar y gestionar alertas."""

    def __init__(self, session: AsyncSession):
        """
        Argumentos:
            session: Sesión asíncrona de SQLAlchemy.
        """
        self.session = session

    async def crear_alerta(self, datos: dict) -> Alert:
        """Crea una nueva alerta (llamado por el motor de correlación).

        Argumentos:
            datos: Dict con los campos de la alerta.

        Retorna:
            La instancia de Alert creada.
        """
        alerta = Alert(**datos)
        self.session.add(alerta)
        await self.session.commit()
        await self.session.refresh(alerta)
        logger.info(
            "Alerta creada: %s | %s | %s",
            alerta.id, alerta.severity, alerta.title,
        )
        return alerta

    async def listar_alertas(
        self,
        limite: int = 50,
        desde: int = 0,
        estado: str | None = None,
        severidad: str | None = None,
    ) -> tuple[list[Alert], int]:
        """Lista alertas con paginación y filtros.

        Argumentos:
            limite: Cantidad máxima de alertas.
            desde: Offset para paginación.
            estado: Filtrar por estado (open, acknowledged, investigating, resolved, false_positive).
            severidad: Filtrar por severidad.

        Retorna:
            Tupla (lista de alertas, total sin paginación).
        """
        query = select(Alert).order_by(Alert.created_at.desc())
        count_query = select(func.count(Alert.id))

        if estado:
            query = query.where(Alert.status == estado)
            count_query = count_query.where(Alert.status == estado)
        if severidad:
            query = query.where(Alert.severity == severidad)
            count_query = count_query.where(Alert.severity == severidad)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        result = await self.session.execute(query.offset(desde).limit(limite))
        alertas = list(result.scalars().all())

        return alertas, total

    async def obtener_alerta(self, alerta_id: str) -> Alert | None:
        """Obtiene una alerta por su ID.

        Argumentos:
            alerta_id: UUID de la alerta.

        Retorna:
            Alert o None si no existe.
        """
        from uuid import UUID
        try:
            result = await self.session.execute(
                select(Alert).where(Alert.id == UUID(alerta_id))
            )
            return result.scalar_one_or_none()
        except (ValueError, Exception) as e:
            logger.warning("Error al obtener alerta %s: %s", alerta_id, e)
            return None

    async def actualizar_estado(
        self, alerta_id: str, nuevo_estado: str, notas: str | None = None
    ) -> Alert | None:
        """Actualiza el estado de una alerta (ciclo de vida).

        Estados: open → acknowledged → investigating → resolved | false_positive

        Argumentos:
            alerta_id: UUID de la alerta.
            nuevo_estado: Nuevo estado.
            notas: Notas de resolución (opcional).

        Retorna:
            Alert actualizada, o None si no existe.
        """
        alerta = await self.obtener_alerta(alerta_id)
        if not alerta:
            return None

        alerta.status = nuevo_estado
        alerta.updated_at = datetime.now(timezone.utc)

        if nuevo_estado in ("resolved", "false_positive"):
            alerta.resolved_at = datetime.now(timezone.utc)

        if notas:
            alerta.resolution_notes = notas

        await self.session.commit()
        await self.session.refresh(alerta)
        logger.info("Alerta %s → estado: %s", alerta_id, nuevo_estado)
        return alerta

    async def actualizar_contadores(
        self, rule_id: str, event_count: int, last_event_at: datetime
    ) -> Alert | None:
        """Actualiza los contadores de una alerta abierta en ventana temporal.

        Busca la alerta más reciente (open) para la regla dada y actualiza
        su event_count y last_event_at. Esto permite que múltiples eventos
        dentro de una ventana de correlación actualicen una misma alerta.

        Argumentos:
            rule_id: UUID de la regla (como string).
            event_count: Nuevo contador de eventos.
            last_event_at: Timestamp del último evento recibido.

        Retorna:
            La alerta actualizada, o None si no encontró ninguna abierta.
        """
        from uuid import UUID
        try:
            result = await self.session.execute(
                select(Alert).where(
                    Alert.rule_id == UUID(rule_id),
                    Alert.status == "open",
                ).order_by(Alert.created_at.desc()).limit(1)
            )
            alerta = result.scalar_one_or_none()
            if not alerta:
                logger.warning(
                    "No se encontró alerta abierta para regla %s", rule_id,
                )
                return None

            alerta.event_count = event_count
            alerta.last_event_at = last_event_at
            await self.session.commit()
            await self.session.refresh(alerta)
            logger.debug(
                "Alerta %s actualizada: %d eventos", alerta.id, event_count,
            )
            return alerta
        except (ValueError, Exception) as e:
            logger.warning("Error actualizando contadores: %s", e)
            return None

    async def obtener_estadisticas(self) -> dict:
        """Obtiene estadísticas de alertas.

        Retorna:
            Dict con conteo por estado y severidad.
        """
        # Total por estado
        total_result = await self.session.execute(
            select(func.count(Alert.id))
        )
        total = total_result.scalar() or 0

        # Abiertas (open + acknowledged + investigating)
        abiertas_result = await self.session.execute(
            select(func.count(Alert.id)).where(
                Alert.status.in_(["open", "acknowledged", "investigating"])
            )
        )
        abiertas = abiertas_result.scalar() or 0

        # Resueltas
        resueltas_result = await self.session.execute(
            select(func.count(Alert.id)).where(
                Alert.status.in_(["resolved", "false_positive"])
            )
        )
        resueltas = resueltas_result.scalar() or 0

        return {
            "total_alertas": total,
            "alertas_abiertas": abiertas,
            "alertas_resueltas": resueltas,
        }
