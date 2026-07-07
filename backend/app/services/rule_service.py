"""Servicio de reglas de detección: CRUD y carga de reglas activas.

Las reglas se almacenan en PostgreSQL y se cachean en memoria
en el motor de correlación para evaluación rápida.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rule import DetectionRule

logger = logging.getLogger(__name__)


class RuleService:
    """Servicio para crear, consultar, actualizar y eliminar reglas."""

    def __init__(self, session: AsyncSession):
        """
        Argumentos:
            session: Sesión asíncrona de SQLAlchemy.
        """
        self.session = session

    async def crear_regla(self, datos: dict) -> DetectionRule:
        """Crea una nueva regla de detección.

        Argumentos:
            datos: Dict con los campos de la regla (title, description, conditions, etc.).

        Retorna:
            La instancia de DetectionRule creada.
        """
        regla = DetectionRule(**datos)
        self.session.add(regla)
        await self.session.commit()
        await self.session.refresh(regla)
        logger.info("Regla creada: %s - %s", regla.id, regla.title)
        return regla

    async def listar_reglas(
        self,
        limite: int = 100,
        desde: int = 0,
        estado: str | None = None,
        severidad: str | None = None,
    ) -> tuple[list[DetectionRule], int]:
        """Lista reglas con paginación y filtros.

        Argumentos:
            limite: Cantidad máxima de reglas.
            desde: Offset.
            estado: Filtrar por estado (active, disabled, test).
            severidad: Filtrar por severidad.

        Retorna:
            Tupla (lista de reglas, total sin paginación).
        """
        query = select(DetectionRule).order_by(DetectionRule.created_at.desc())
        count_query = select(func.count(DetectionRule.id))

        if estado:
            query = query.where(DetectionRule.status == estado)
            count_query = count_query.where(DetectionRule.status == estado)
        if severidad:
            query = query.where(DetectionRule.severity == severidad)
            count_query = count_query.where(DetectionRule.severity == severidad)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        result = await self.session.execute(query.offset(desde).limit(limite))
        reglas = list(result.scalars().all())

        return reglas, total

    async def obtener_regla(self, regla_id: str) -> DetectionRule | None:
        """Obtiene una regla por su ID.

        Argumentos:
            regla_id: UUID de la regla.

        Retorna:
            DetectionRule o None si no existe.
        """
        from uuid import UUID

        try:
            result = await self.session.execute(
                select(DetectionRule).where(DetectionRule.id == UUID(regla_id))
            )
            return result.scalar_one_or_none()
        except (ValueError, Exception) as e:
            logger.warning("Error al obtener regla %s: %s", regla_id, e)
            return None

    async def actualizar_regla(
        self, regla_id: str, datos: dict
    ) -> DetectionRule | None:
        """Actualiza una regla existente.

        Argumentos:
            regla_id: UUID de la regla.
            datos: Dict con los campos a actualizar.

        Retorna:
            DetectionRule actualizada, o None si no existe.
        """
        regla = await self.obtener_regla(regla_id)
        if not regla:
            return None

        for key, value in datos.items():
            if hasattr(regla, key) and value is not None:
                setattr(regla, key, value)

        regla.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(regla)
        logger.info("Regla actualizada: %s", regla_id)
        return regla

    async def eliminar_regla(self, regla_id: str) -> bool:
        """Elimina una regla por su ID.

        Argumentos:
            regla_id: UUID de la regla.

        Retorna:
            True si se eliminó, False si no existía.
        """
        from uuid import UUID

        try:
            result = await self.session.execute(
                delete(DetectionRule).where(DetectionRule.id == UUID(regla_id))
            )
            await self.session.commit()
            eliminado = result.rowcount > 0
            if eliminado:
                logger.info("Regla eliminada: %s", regla_id)
            return eliminado
        except (ValueError, Exception) as e:
            logger.warning("Error al eliminar regla %s: %s", regla_id, e)
            return False

    async def cargar_reglas_activas(self) -> list[DetectionRule]:
        """Carga todas las reglas activas para el motor de correlación.

        Este método se usa al iniciar la aplicación para poblar
        el caché del CorrelationEngine.

        Retorna:
            Lista de reglas con status='active'.
        """
        result = await self.session.execute(
            select(DetectionRule).where(DetectionRule.status == "active")
        )
        return list(result.scalars().all())
