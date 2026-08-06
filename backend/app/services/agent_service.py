"""Remote agent service: CRUD, API key generation, authentication.

Each agent has an API key generated with secrets.token_urlsafe(32),
hashed with bcrypt before persisting. The plaintext key is returned
ONLY ONCE in the creation response.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


class AgentService:
    """Service for creating, listing, deactivating and authenticating agents."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── API Key generation ─────────────────────────────────────────────────

    @staticmethod
    def _generar_api_key() -> str:
        """Generate a secure API key with the spy_ prefix.

        Uses secrets.token_urlsafe(32) which produces ~43 characters
        of URL-safe alphanumeric content.
        """
        return f"spy_{secrets.token_urlsafe(32)}"

    # ── CRUD ──────────────────────────────────────────────────────────────

    async def crear_agente(
        self,
        name: str,
        hostname: str,
        version: str | None = None,
    ) -> tuple[Agent, str]:
        """Create a new agent with an automatically generated API key.

        The API key is generated, hashed with bcrypt, and the hash
        is persisted. The plaintext key is returned in the tuple so
        the caller can show it to the user ONLY ONCE.

        Args:
            name: Unique agent name.
            hostname: Hostname of the agent's machine.
            version: Agent software version (optional).

        Returns:
            Tuple (Agent, raw_api_key).

        Raises:
            ValueError: If an agent with that name already exists.
        """
        nombre = name.strip()

        # Check for duplicates
        existe = await self.session.execute(select(Agent).where(Agent.name == nombre))
        if existe.scalar_one_or_none():
            raise ValueError(f"Agent '{nombre}' already exists")

        # Generate API key
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

        logger.info("Agent created: %s (hostname: %s)", agente.name, agente.hostname)
        return agente, raw_key

    async def listar_agentes(
        self,
        solo_activos: bool = False,
        page: int = 1,
        per_page: int = 10,
    ) -> tuple[list[Agent], int]:
        """List registered agents with pagination, optionally only the active ones.

        Args:
            solo_activos: If True, filters only agents with active=True.
            page: Page number (starts at 1).
            per_page: Number of agents per page.

        Returns:
            Tuple (list of agents for the current page, total agents).
        """
        query = select(Agent).order_by(Agent.created_at.desc())
        count_query = select(func.count(Agent.id))

        if solo_activos:
            query = query.where(Agent.active.is_(True))
            count_query = count_query.where(Agent.active.is_(True))

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.limit(per_page).offset((page - 1) * per_page)
        result = await self.session.execute(query)
        agentes = list(result.scalars().all())

        return agentes, total

    async def desactivar_agente(self, agent_id: int) -> bool:
        """Deactivate an agent by its ID.

        Args:
            agent_id: ID of the agent to deactivate.

        Returns:
            True if it was deactivated, False if not found.
        """
        agente = await self.session.get(Agent, agent_id)
        if not agente:
            return False

        agente.active = False
        await self.session.commit()
        logger.info("Agent deactivated: %s (id=%d)", agente.name, agent_id)
        return True

    async def obtener_por_api_key(self, api_key: str) -> Agent | None:
        """Find an agent by its API key (bcrypt verify).

        Iterates over ALL agents and verifies the key
        against each hash with bcrypt. Does not filter by active —
        the caller (require_agent) handles the status check.

        Args:
            api_key: Plaintext API key to verify.

        Returns:
            Agent if a match is found (active or not), None otherwise.
        """
        result = await self.session.execute(select(Agent))
        for agente in result.scalars().all():
            if AuthService.verify_password(api_key, agente.api_key_hash):
                return agente
        return None

    async def obtener_por_id(self, agent_id: int) -> Agent | None:
        """Get an agent by its ID.

        Args:
            agent_id: ID of the agent to look up.

        Returns:
            Agent if it exists, None otherwise.
        """
        return await self.session.get(Agent, agent_id)

    async def actualizar_agente(
        self,
        agent_id: int,
        name: str | None = None,
        hostname: str | None = None,
    ) -> Agent | None:
        """Update agent fields (name, hostname).

        Only updates the fields passed as arguments.
        Unspecified fields keep their current value.

        Args:
            agent_id: ID of the agent to update.
            name: New name (optional).
            hostname: New hostname (optional).

        Returns:
            Updated Agent if it exists, None if not found.
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
        logger.info("Agent updated: %s (id=%d)", agente.name, agent_id)
        return agente

    async def eliminar_agente(self, agent_id: int) -> bool:
        """Delete an agent by its ID.

        Args:
            agent_id: ID of the agent to delete.

        Returns:
            True if it was deleted, False if not found.
        """
        agente = await self.session.get(Agent, agent_id)
        if not agente:
            return False

        await self.session.delete(agente)
        await self.session.commit()
        logger.info("Agent deleted: %s (id=%d)", agente.name, agent_id)
        return True

    async def desactivar_inactivos(self) -> int:
        """Deactivate agents whose heartbeat has expired.

        Looks up agents with active=True whose last_seen is before
        (now - heartbeat_timeout_minutes). If last_seen is
        None (never sent a heartbeat), they are also deactivated.

        Returns:
            Number of deactivated agents.
        """
        ahora = datetime.now(UTC)

        # Get all active agents
        result = await self.session.execute(select(Agent).where(Agent.active.is_(True)))
        agentes_activos = list(result.scalars().all())

        desactivados = 0
        for agente in agentes_activos:
            timeout = timedelta(minutes=agente.heartbeat_timeout_minutes)
            limite = ahora - timeout

            # If it has no last_seen or is expired → deactivate
            if agente.last_seen is None or agente.last_seen < limite:
                agente.active = False
                desactivados += 1
                logger.info(
                    "Agent deactivated by heartbeat timeout: %s (id=%d, "
                    "last_seen=%s, timeout=%d min)",
                    agente.name,
                    agente.id,
                    agente.last_seen,
                    agente.heartbeat_timeout_minutes,
                )

        if desactivados > 0:
            await self.session.commit()

        return desactivados
