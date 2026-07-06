"""Servicio de agentes remotos: CRUD, API key generation, autenticación.

Cada agente tiene una API key generada con secrets.token_urlsafe(32),
hasheada con bcrypt antes de persistir. La key plaintext se retorna
UNA SOLA VEZ en la respuesta de creación.
"""

import logging
import secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


class AgentService:
    """Servicio para crear, listar, desactivar y autenticar agentes."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── API Key generation ─────────────────────────────────────────────────

    @staticmethod
    def _generar_api_key() -> str:
        """Genera una API key segura con prefijo spy_.

        Usa secrets.token_urlsafe(32) que produce ~43 caracteres
        alfanuméricos seguros para URL.
        """
        return f"spy_{secrets.token_urlsafe(32)}"

    # ── CRUD ──────────────────────────────────────────────────────────────

    async def crear_agente(
        self,
        name: str,
        hostname: str,
        version: str | None = None,
    ) -> tuple[Agent, str]:
        """Crea un nuevo agente con API key generada automáticamente.

        La API key se genera, se hashea con bcrypt, y se persiste
        el hash. La key plaintext se retorna en la tupla para que
        el caller la muestre al usuario UNA SOLA VEZ.

        Args:
            name: Nombre único del agente.
            hostname: Hostname del equipo del agente.
            version: Versión del software agente (opcional).

        Returns:
            Tupla (Agent, raw_api_key).

        Raises:
            ValueError: Si ya existe un agente con ese nombre.
        """
        nombre = name.strip()

        # Verificar duplicado
        existe = await self.session.execute(
            select(Agent).where(Agent.name == nombre)
        )
        if existe.scalar_one_or_none():
            raise ValueError(f"El agente '{nombre}' ya existe")

        # Generar API key
        raw_key = self._generar_api_key()
        api_key_hash = AuthService.hash_password(raw_key)

        agente = Agent(
            name=nombre,
            hostname=hostname.strip(),
            api_key_hash=api_key_hash,
            active=True,
            version=version,
        )
        self.session.add(agente)
        await self.session.commit()
        await self.session.refresh(agente)

        logger.info("Agente creado: %s (hostname: %s)", agente.name, agente.hostname)
        return agente, raw_key

    async def listar_agentes(
        self,
        solo_activos: bool = False,
    ) -> tuple[list[Agent], int]:
        """Lista agentes registrados, opcionalmente solo los activos.

        Args:
            solo_activos: Si True, filtra solo agentes con active=True.

        Returns:
            Tupla (lista de agentes, total).
        """
        query = select(Agent).order_by(Agent.created_at.desc())
        count_query = select(func.count(Agent.id))

        if solo_activos:
            query = query.where(Agent.active.is_(True))
            count_query = count_query.where(Agent.active.is_(True))

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        result = await self.session.execute(query)
        agentes = list(result.scalars().all())

        return agentes, total

    async def desactivar_agente(self, agent_id: int) -> bool:
        """Desactiva un agente por su ID.

        Args:
            agent_id: ID del agente a desactivar.

        Returns:
            True si se desactivó, False si no se encontró.
        """
        agente = await self.session.get(Agent, agent_id)
        if not agente:
            return False

        agente.active = False
        await self.session.commit()
        logger.info("Agente desactivado: %s (id=%d)", agente.name, agent_id)
        return True

    async def obtener_por_api_key(self, api_key: str) -> Agent | None:
        """Busca un agente por su API key (bcrypt verify).

        Itera sobre TODOS los agentes y verifica la key
        contra cada hash con bcrypt. No filtra por active —
        el llamante (require_agent) maneja el chequeo de estado.

        Args:
            api_key: API key plaintext a verificar.

        Returns:
            Agent si encuentra match (activo o no), None en caso contrario.
        """
        result = await self.session.execute(
            select(Agent)
        )
        for agente in result.scalars().all():
            if AuthService.verify_password(api_key, agente.api_key_hash):
                return agente
        return None

    async def obtener_por_id(self, agent_id: int) -> Agent | None:
        """Obtiene un agente por su ID.

        Args:
            agent_id: ID del agente a buscar.

        Returns:
            Agent si existe, None en caso contrario.
        """
        return await self.session.get(Agent, agent_id)

    async def actualizar_agente(
        self,
        agent_id: int,
        name: str | None = None,
        hostname: str | None = None,
    ) -> Agent | None:
        """Actualiza campos de un agente (name, hostname).

        Solo actualiza los campos que se pasan como argumento.
        Los campos no especificados mantienen su valor actual.

        Args:
            agent_id: ID del agente a actualizar.
            name: Nuevo nombre (opcional).
            hostname: Nuevo hostname (opcional).

        Returns:
            Agent actualizado si existe, None si no se encontró.
        """
        agente = await self.session.get(Agent, agent_id)
        if not agente:
            return None

        if name is not None:
            agente.name = name.strip()
        if hostname is not None:
            agente.hostname = hostname.strip()

        await self.session.commit()
        await self.session.refresh(agente)
        logger.info("Agente actualizado: %s (id=%d)", agente.name, agent_id)
        return agente

    async def eliminar_agente(self, agent_id: int) -> bool:
        """Elimina un agente por su ID.

        Args:
            agent_id: ID del agente a eliminar.

        Returns:
            True si se eliminó, False si no se encontró.
        """
        agente = await self.session.get(Agent, agent_id)
        if not agente:
            return False

        await self.session.delete(agente)
        await self.session.commit()
        logger.info("Agente eliminado: %s (id=%d)", agente.name, agent_id)
        return True

    async def desactivar_inactivos(self) -> int:
        """Desactiva agentes cuyo heartbeat ha expirado.

        Busca agents con active=True cuyo last_seen es anterior
        a (ahora - heartbeat_timeout_minutes). Si last_seen es
        None (nunca hicieron heartbeat), también se desactivan.

        Returns:
            Número de agentes desactivados.
        """
        ahora = datetime.now(timezone.utc)

        # Obtener todos los agentes activos
        result = await self.session.execute(
            select(Agent).where(Agent.active.is_(True))
        )
        agentes_activos = list(result.scalars().all())

        desactivados = 0
        for agente in agentes_activos:
            timeout = timedelta(minutes=agente.heartbeat_timeout_minutes)
            limite = ahora - timeout

            # Si no tiene last_seen o está vencido → desactivar
            if agente.last_seen is None or agente.last_seen < limite:
                agente.active = False
                desactivados += 1
                logger.info(
                    "Agente desactivado por heartbeat timeout: %s (id=%d, "
                    "last_seen=%s, timeout=%d min)",
                    agente.name, agente.id, agente.last_seen,
                    agente.heartbeat_timeout_minutes,
                )

        if desactivados > 0:
            await self.session.commit()

        return desactivados
