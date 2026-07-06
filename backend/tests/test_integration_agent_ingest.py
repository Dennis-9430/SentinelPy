"""Tests de integración para agent ingest (POST /api/v2/events + POST heartbeat).

Verifica batch ingest con pipeline, heartbeat, y auth failures
contra PostgreSQL real via Testcontainers.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from app.services.agent_service import AgentService


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app():
    """Fixture que provee la instancia de la aplicación FastAPI."""
    from app.main import app
    return app


@pytest_asyncio.fixture
async def agent_client_and_auth(app, session, async_engine):
    """Crea un agente de prueba + httpx client con session override + pipeline.

    El agente se crea via AgentService directamente, y la API key
    se pasa como Bearer token en cada request.
    El pipeline se configura para usar el testcontainer DB.
    """
    from app.database import get_session
    from app.services.pipeline import Pipeline
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    # Crear pipeline que apunte al testcontainer
    factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False,
    )
    pipeline = Pipeline(engine=None, session_factory=factory)
    app.state.pipeline = pipeline

    # Crear agente con la sesión del test
    service = AgentService(session)
    agente, raw_key = await service.crear_agente(
        name="test-ingest-agent",
        hostname="test-agent-host",
    )

    # Override get_session para que use el session del test
    async def _override_get_session():
        return session

    app.dependency_overrides[get_session] = _override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, raw_key, agente

    app.dependency_overrides.clear()
    if hasattr(app.state, "pipeline"):
        del app.state.pipeline


# ── Helpers ────────────────────────────────────────────────────────────────

EVENTO_BASE = {
    "source_ip": "10.0.0.1",
    "event_type": "login_attempt",
    "severity": "medium",
    "message": "Intento de login desde IP externa",
}


def _evento_valido(**kwargs) -> dict:
    """Retorna un dict de evento válido, combinado con kwargs."""
    data = dict(EVENTO_BASE)
    data.update(kwargs)
    return data


# ── Tests: POST /api/v2/events ─────────────────────────────────────────────

class TestAgentIngestV2:
    """Prueba POST /api/v2/events — batch ingest autenticado."""

    @pytest.mark.asyncio
    async def test_batch_exitoso(self, agent_client_and_auth):
        """Batch de 3 eventos válidos se procesa y retorna IDs."""
        client, api_key, _ = agent_client_and_auth
        eventos = [
            _evento_valido(source_ip=f"10.0.0.{i}")
            for i in range(3)
        ]
        response = await client.post(
            "/api/v2/events",
            json={"events": eventos},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["processed"] == 3
        assert data["failed"] == 0
        assert len(data["event_ids"]) == 3
        for eid in data["event_ids"]:
            assert isinstance(eid, str) and len(eid) > 0

    @pytest.mark.asyncio
    async def test_batch_hasta_100_eventos(self, agent_client_and_auth):
        """Batch con 100 eventos se procesa correctamente."""
        client, api_key, _ = agent_client_and_auth
        eventos = [_evento_valido(source_ip=f"10.0.0.{i}") for i in range(100)]
        response = await client.post(
            "/api/v2/events",
            json={"events": eventos},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["processed"] == 100
        assert data["failed"] == 0
        assert len(data["event_ids"]) == 100

    @pytest.mark.asyncio
    async def test_batch_vacio_retorna_400(self, agent_client_and_auth):
        """Batch vacío retorna 400."""
        client, api_key, _ = agent_client_and_auth
        response = await client.post(
            "/api/v2/events",
            json={"events": []},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_batch_campos_requeridos_faltan_retorna_400(
        self, agent_client_and_auth,
    ):
        """Evento sin event_type/severity/message retorna 400.

        El batch completo se rechaza — ningún evento se persiste."""
        client, api_key, _ = agent_client_and_auth
        response = await client.post(
            "/api/v2/events",
            json={"events": [{"source_ip": "10.0.0.1"}]},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_batch_solo_un_evento(self, agent_client_and_auth):
        """Batch con un solo evento funciona."""
        client, api_key, _ = agent_client_and_auth
        response = await client.post(
            "/api/v2/events",
            json={"events": [_evento_valido()]},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["processed"] == 1
        assert data["failed"] == 0
        assert len(data["event_ids"]) == 1

    @pytest.mark.asyncio
    async def test_batch_sin_auth_retorna_401(self, agent_client_and_auth):
        """POST /api/v2/events sin Bearer token retorna 401.
        Sin Bearer token → require_agent retorna 401 sin consultar DB."""
        client, _, _ = agent_client_and_auth
        response = await client.post(
            "/api/v2/events",
            json={"events": [_evento_valido()]},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_batch_token_invalido_retorna_401(self, agent_client_and_auth):
        """POST /api/v2/events con token inválido retorna 401."""
        client, _, _ = agent_client_and_auth
        response = await client.post(
            "/api/v2/events",
            json={"events": [_evento_valido()]},
            headers={"Authorization": "Bearer spy_key_invalida_12345"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_batch_eventos_persistidos_en_db(
        self, agent_client_and_auth, session,
    ):
        """Eventos enviados se persisten en la base de datos con collector_type=agent."""
        from app.models.event import NormalizedEvent
        from sqlalchemy import select

        client, api_key, agent = agent_client_and_auth
        eventos = [
            _evento_valido(source_ip="10.0.0.1", event_type="auth_failure"),
            _evento_valido(source_ip="10.0.0.2", event_type="port_scan"),
        ]
        response = await client.post(
            "/api/v2/events",
            json={"events": eventos},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 201, response.text

        # Verificar en DB
        result = await session.execute(select(NormalizedEvent))
        db_events = list(result.scalars().all())
        assert len(db_events) == 2
        for ev in db_events:
            assert ev.collector_type == "agent"
            # source debe ser el hostname del agente (no se proveyó source propio)
            assert ev.source == "test-agent-host"

    @pytest.mark.asyncio
    async def test_batch_source_respetado_si_provisto(
        self, agent_client_and_auth, session,
    ):
        """Si el evento tiene source propio, se respeta (no el hostname del agente)."""
        from app.models.event import NormalizedEvent
        from sqlalchemy import select, func

        client, api_key, agent = agent_client_and_auth
        response = await client.post(
            "/api/v2/events",
            json={"events": [_evento_valido(source="mi-propio-source")]},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 201, response.text

        result = await session.execute(
            select(NormalizedEvent).where(
                NormalizedEvent.source == "mi-propio-source"
            )
        )
        ev = result.scalar_one_or_none()
        assert ev is not None
        assert ev.source == "mi-propio-source"
        assert ev.collector_type == "agent"


# ── Tests: POST /api/v2/agent/heartbeat ────────────────────────────────────

class TestAgentHeartbeat:
    """Prueba POST /api/v2/agent/heartbeat."""

    @pytest.mark.asyncio
    async def test_heartbeat_exitoso(self, agent_client_and_auth, session):
        """Heartbeat exitoso retorna status=ok y actualiza last_seen."""
        client, api_key, agent = agent_client_and_auth

        response = await client.post(
            "/api/v2/agent/heartbeat",
            json={
                "hostname": agent.hostname,
                "os": "linux",
                "agent_version": "1.0.0",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "ok"
        assert "server_time" in data
        # Verificar ISO timestamp válido
        ts = datetime.fromisoformat(data["server_time"].replace("Z", "+00:00"))
        assert ts.tzinfo is not None

        # Verificar que last_seen se actualizó
        await session.refresh(agent)
        assert agent.last_seen is not None

    @pytest.mark.asyncio
    async def test_heartbeat_sin_auth_retorna_401(self, agent_client_and_auth):
        """Heartbeat sin Bearer token retorna 401."""
        client, _, _ = agent_client_and_auth
        response = await client.post(
            "/api/v2/agent/heartbeat",
            json={
                "hostname": "test",
                "os": "linux",
                "agent_version": "1.0.0",
            },
        )
        assert response.status_code == 401
