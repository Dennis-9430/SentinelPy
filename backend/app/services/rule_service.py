"""Detection rule service: CRUD and loading of active rules.

Rules are stored in PostgreSQL and cached in memory
in the correlation engine for fast evaluation.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rule import DetectionRule

logger = logging.getLogger(__name__)


class RuleService:
    """Service for creating, querying, updating and deleting rules."""

    def __init__(self, session: AsyncSession):
        """
        Args:
            session: Async SQLAlchemy session.
        """
        self.session = session

    async def crear_regla(self, datos: dict) -> DetectionRule:
        """Create a new detection rule.

        Args:
            datos: Dict with the rule fields (title, description, conditions, etc.).

        Returns:
            The created DetectionRule instance.
        """
        regla = DetectionRule(**datos)
        self.session.add(regla)
        await self.session.commit()
        await self.session.refresh(regla)
        logger.info("Rule created: %s - %s", regla.id, regla.title)
        return regla

    async def listar_reglas(
        self,
        limite: int = 100,
        desde: int = 0,
        estado: str | None = None,
        severidad: str | None = None,
    ) -> tuple[list[DetectionRule], int]:
        """List rules with pagination and filters.

        Args:
            limite: Maximum number of rules.
            desde: Offset.
            estado: Filter by status (active, disabled, test).
            severidad: Filter by severity.

        Returns:
            Tuple (list of rules, total without pagination).
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
        """Get a rule by its ID.

        Args:
            regla_id: UUID of the rule.

        Returns:
            DetectionRule or None if it does not exist.
        """
        from uuid import UUID

        try:
            result = await self.session.execute(
                select(DetectionRule).where(DetectionRule.id == UUID(regla_id))
            )
            return result.scalar_one_or_none()
        except (ValueError, Exception) as e:
            logger.warning("Error getting rule %s: %s", regla_id, e)
            return None

    async def actualizar_regla(
        self, regla_id: str, datos: dict
    ) -> DetectionRule | None:
        """Update an existing rule.

        Args:
            regla_id: UUID of the rule.
            datos: Dict with the fields to update.

        Returns:
            Updated DetectionRule, or None if it does not exist.
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
        logger.info("Rule updated: %s", regla_id)
        return regla

    async def eliminar_regla(self, regla_id: str) -> bool:
        """Delete a rule by its ID.

        Args:
            regla_id: UUID of the rule.

        Returns:
            True if it was deleted, False if it did not exist.
        """
        from uuid import UUID

        try:
            result = await self.session.execute(
                delete(DetectionRule).where(DetectionRule.id == UUID(regla_id))
            )
            await self.session.commit()
            eliminado = result.rowcount > 0
            if eliminado:
                logger.info("Rule deleted: %s", regla_id)
            return eliminado
        except (ValueError, Exception) as e:
            logger.warning("Error deleting rule %s: %s", regla_id, e)
            return False

    async def cargar_reglas_activas(self) -> list[DetectionRule]:
        """Load all active rules for the correlation engine.

        This method is used at application startup to populate
        the CorrelationEngine cache.

        Returns:
            List of rules with status='active'.
        """
        result = await self.session.execute(
            select(DetectionRule).where(DetectionRule.status == "active")
        )
        return list(result.scalars().all())
