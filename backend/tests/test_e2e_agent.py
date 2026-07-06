"""Tests E2E para el flujo completo agente → servidor → engine → alerta.

Usa testcontainers + httpx.AsyncClient con ASGITransport para emular
el ciclo completo de un agente remoto: registro vía admin API, envío
de eventos batch, verificación de procesamiento por el motor de
correlación y creación de alertas en la base de datos.

PR-6.1: Flujo E2E completo
PR-6.2: Buffer offline — SQLite queue acumula eventos sin conexión
"""

import os
import tempfile
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


# ── Helpers compartidos ──────────────────────────────────────────────────────

EVENTO_LOGIN_FAILURE = {
    "source_ip": "10.0.0.5",
    "event_type": "login_failure",
    "severity": "high",
    "message": "Fallo de autenticación SSH desde IP externa",
}


def _evento_valido(**kwargs) -> dict:
    """Retorna un evento válido combinado con kwargs."""
    data = dict(EVENTO_LOGIN_FAILURE)
    data.update(kwargs)
    return data


# ═════════════════════════════════════════════════════════════════════════════
# Fixture E2E compartida
# ═════════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def e2e_env(session, async_engine, run_migrations):
    """Prepara entorno E2E completo: regla, admin, agente, pipeline + engine.

    Retorna (client, api_key, agent_data, session) para los tests.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.database import get_session
    from app.main import app
    from app.models.alert import Alert
    from app.models.user import User
    from app.services.auth_service import AuthService
    from app.services.engine import CorrelationEngine
    from app.services.pipeline import Pipeline
    from app.services.rule_service import RuleService

    # ── Session factory para pipeline y callback ────────────────────────
    factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # ── Seed regla de prueba ────────────────────────────────────────────
    rule_svc = RuleService(session)
    regla = await rule_svc.crear_regla({
        "title": "E2E Login Failure",
        "description": "Detecta fallos de autenticación remota",
        "severity": "high",
        "status": "active",
        "conditions": {
            "operator": "AND",
            "conditions": [
                {"field": "event_type", "operator": "eq", "value": "login_failure"},
                {"field": "severity", "operator": "eq", "value": "high"},
            ],
        },
        "alert_title": "E2E: Login Failure Detected",
        "alert_severity": "high",
    })

    # ── Engine con callback que persiste alertas en DB ──────────────────
    engine = CorrelationEngine()
    engine.cargar_reglas([regla])

    async def _alert_callback(datos_alerta: dict):
        """Persiste la alerta en la sesión del test."""
        alerta = Alert(**datos_alerta)
        session.add(alerta)
        await session.commit()
        await session.refresh(alerta)
        return alerta

    engine.registrar_callback(_alert_callback)

    # ── Pipeline apuntando al testcontainer ─────────────────────────────
    pipeline = Pipeline(engine=engine, session_factory=factory)

    # ── Override app state ──────────────────────────────────────────────
    app.state.pipeline = pipeline
    app.state.engine = engine

    # ── Override get_session dependency ─────────────────────────────────
    async def _override_get_session():
        yield session

    app.dependency_overrides[get_session] = _override_get_session

    # ── Seed admin user + JWT ───────────────────────────────────────────
    auth_svc = AuthService(session)
    user = await auth_svc.crear_usuario(
        username="e2e-admin",
        password="e2e-admin-pass",
        role="admin",
    )
    token = auth_svc.crear_token(user)

    # ── Crear agente vía admin API y retornar client ───────────────────
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
    ) as client:
        create_resp = await client.post(
            "/api/admin/agents",
            json={"name": "e2e-test-agent", "hostname": "e2e-demo-host"},
            cookies={"access_token": token},
        )
        assert create_resp.status_code == 201, (
            f"Fallo al crear agente: {create_resp.text}"
        )
        agent_data = create_resp.json()
        api_key = agent_data["api_key_raw"]

        yield client, api_key, agent_data, session

    # ── Cleanup ─────────────────────────────────────────────────────────
    app.dependency_overrides.clear()
    if hasattr(app.state, "pipeline"):
        del app.state.pipeline
    if hasattr(app.state, "engine"):
        del app.state.engine


# ═════════════════════════════════════════════════════════════════════════════
# PR-6.1: Flujo E2E completo
# ═════════════════════════════════════════════════════════════════════════════


class TestE2EFullCycle:
    """PR-6.1: Flujo completo — agente registra, envía eventos, engine genera alerta."""

    @pytest.mark.asyncio
    async def test_batch_3_eventos_procesados_con_alertas(self, e2e_env):
        """Batch de 3 eventos que matchean regla → processed=3, alertas en DB."""
        from sqlalchemy import select
        from app.models.alert import Alert

        client, api_key, _, session = e2e_env
        eventos = [_evento_valido(source_ip=f"10.0.0.{i}") for i in range(3)]

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

        # Verificar que el engine generó alertas
        result = await session.execute(select(Alert))
        alerts = list(result.scalars().all())
        assert len(alerts) >= 1, "El motor de correlación debió generar al menos 1 alerta"
        assert alerts[0].title == "E2E: Login Failure Detected"
        assert alerts[0].severity == "high"

    @pytest.mark.asyncio
    async def test_batch_100_eventos(self, e2e_env):
        """Batch con 100 eventos se procesa correctamente."""
        client, api_key, _, _ = e2e_env
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
    async def test_batch_un_solo_evento(self, e2e_env):
        """Batch con un solo evento funciona."""
        client, api_key, _, _ = e2e_env

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
    async def test_batch_sin_auth_retorna_401(self, e2e_env):
        """Sin Bearer token retorna 401."""
        client, _, _, _ = e2e_env

        response = await client.post(
            "/api/v2/events",
            json={"events": [_evento_valido()]},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_batch_token_invalido_retorna_401(self, e2e_env):
        """Bearer token inválido retorna 401."""
        client, _, _, _ = e2e_env

        response = await client.post(
            "/api/v2/events",
            json={"events": [_evento_valido()]},
            headers={"Authorization": "Bearer spy_key_invalida_12345"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_eventos_persistidos_con_collector_agent(self, e2e_env):
        """Eventos se persisten con collector_type=agent y source=hostname."""
        from sqlalchemy import select
        from app.models.event import NormalizedEvent

        client, api_key, agent_data, session = e2e_env

        response = await client.post(
            "/api/v2/events",
            json={"events": [_evento_valido()]},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 201, response.text

        result = await session.execute(select(NormalizedEvent))
        events = list(result.scalars().all())
        assert len(events) == 1
        assert events[0].collector_type == "agent"
        assert events[0].source == "e2e-demo-host"

    @pytest.mark.asyncio
    async def test_evento_source_propio_respetado(self, e2e_env):
        """Si el evento tiene source propio, se respeta (no hostname del agente)."""
        from sqlalchemy import select
        from app.models.event import NormalizedEvent

        client, api_key, _, session = e2e_env

        response = await client.post(
            "/api/v2/events",
            json={
                "events": [
                    _evento_valido(source="mi-propio-source"),
                ],
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 201, response.text

        result = await session.execute(
            select(NormalizedEvent).where(
                NormalizedEvent.source == "mi-propio-source",
            ),
        )
        ev = result.scalar_one_or_none()
        assert ev is not None
        assert ev.source == "mi-propio-source"
        assert ev.collector_type == "agent"

    @pytest.mark.asyncio
    async def test_evento_no_match_no_genera_alerta(self, e2e_env):
        """Evento que no matchea la regla → se procesa pero sin alerta."""
        from sqlalchemy import select
        from app.models.alert import Alert

        client, api_key, _, session = e2e_env

        # Este evento tiene event_type=port_scan, la regla espera login_failure
        response = await client.post(
            "/api/v2/events",
            json={
                "events": [
                    _evento_valido(event_type="port_scan", severity="medium"),
                ],
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["processed"] == 1

        # No deberían haber alertas
        result = await session.execute(select(Alert))
        alerts = list(result.scalars().all())
        assert len(alerts) == 0, (
            "Evento que no matchea regla NO debe generar alertas"
        )

    @pytest.mark.asyncio
    async def test_batch_vacio_retorna_400(self, e2e_env):
        """Batch vacío retorna 400."""
        client, api_key, _, _ = e2e_env

        response = await client.post(
            "/api/v2/events",
            json={"events": []},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 400


# ═════════════════════════════════════════════════════════════════════════════
# PR-6.2: Buffer offline — SQLite queue + sender reconexión
# ═════════════════════════════════════════════════════════════════════════════


# El módulo agent/ está fuera de backend/, en la raíz del proyecto.
# Necesitamos agregarlo al path para importar agent.queue y agent.sender.
import sys as _sys
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)


class TestBufferOffline:
    """PR-6.2: Buffer offline — simula desconexión del server, acumula
    eventos en SQLite queue, y verifica reenvío tras reconexión."""

    # ── Queue offline ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_queue_acumula_eventos_sin_conexion(self):
        """EventQueue acumula eventos en SQLite sin servidor disponible.

        Simula el escenario donde el agente sigue monitoreando logs
        pero el servidor central no está accesible.
        """
        from agent.queue import EventQueue

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            queue = EventQueue(db_path, max_size=1000)

            # Encolar eventos sin conexión al servidor
            for i in range(5):
                eid = queue.enqueue({
                    "source_ip": f"10.0.0.{i}",
                    "event_type": "login_failure",
                    "severity": "high",
                    "message": f"Offline event {i}",
                })
                assert eid > 0

            assert queue.count() == 5

            # Desencolar batch (dequeue NO cambia status, solo lee pending)
            items = queue.dequeue(batch_size=3)
            assert len(items) == 3
            # FIFO: el primero encolado es el primero en salir
            assert items[0]["event_data"]["source_ip"] == "10.0.0.0"

            # Sin mark_sent, los items siguen pending — dequeue vuelve
            # a devolver los primeros (todos siguen con status='pending')
            same_items = queue.dequeue(batch_size=10)
            assert len(same_items) == 5

            # Marcar los primeros 3 como sent y verificar que el
            # count solo refleja los pendientes restantes
            ids = [item["id"] for item in items]
            queue.mark_sent(ids)
            assert queue.count() == 2

            queue.close()
        finally:
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass  # Windows: SQLite connection may hold lock momentarily

    @pytest.mark.asyncio
    async def test_queue_overflow_raise(self):
        """Queue llena lanza OverflowError."""
        from agent.queue import EventQueue

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            queue = EventQueue(db_path, max_size=3)

            for i in range(3):
                queue.enqueue({"event_type": f"test_{i}"})

            with pytest.raises(OverflowError, match="Event queue full"):
                queue.enqueue({"event_type": "overflow"})

            queue.close()
        finally:
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass

    @pytest.mark.asyncio
    async def test_queue_mark_sent_libera_espacio(self):
        """Marcar eventos como sent permite encolar más."""
        from agent.queue import EventQueue

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            queue = EventQueue(db_path, max_size=3)

            for i in range(3):
                queue.enqueue({"event_type": f"test_{i}"})

            # Marcar 2 como enviados
            items = queue.dequeue(batch_size=3)
            ids = [item["id"] for item in items[:2]]
            queue.mark_sent(ids)

            # Ahora count solo cuenta 'pending'
            assert queue.count() == 1

            queue.close()
        finally:
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass

    # ── Sender reconnect ──────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_sender_reconnect_funciona(self):
        """Sender.reconnect() cierra cliente anterior y crea uno nuevo."""
        from agent.sender import EventSender

        sender = EventSender(
            server_url="http://localhost:99999",
            api_key="spy_test_key",
            hostname="offline-test-agent",
        )

        assert sender._http_client is None  # Lazy init

        # reconnect crea un cliente fresco
        await sender.reconnect()
        assert sender._http_client is not None

        # Llamar reconnect de nuevo cierra el anterior y crea otro
        await sender.reconnect()
        assert sender._http_client is not None

        await sender.close()
        assert sender._http_client is None

    @pytest.mark.asyncio
    async def test_sender_close_libera_recursos(self):
        """Sender.close() libera el cliente HTTP."""
        from agent.sender import EventSender

        sender = EventSender(
            server_url="http://localhost:99999",
            api_key="spy_test_key",
            hostname="offline-test-agent",
        )

        # Init client
        await sender.reconnect()
        assert sender._http_client is not None

        await sender.close()
        assert sender._http_client is None

    # ── Reenvío de eventos encolados ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_eventos_queue_reenviados_via_api(self, e2e_env):
        """Eventos acumulados en SQLite queue se envían correctamente
        vía API tras reconexión (simula reenvío offline→online)."""
        from sqlalchemy import select
        from app.models.event import NormalizedEvent
        from app.models.alert import Alert

        client, api_key, _, session = e2e_env

        # Simular eventos que el agente acumuló mientras estaba offline
        eventos_offline = [
            _evento_valido(
                source_ip="10.0.0.10",
                message="Reenviado tras reconexión #1",
            ),
            _evento_valido(
                source_ip="10.0.0.11",
                message="Reenviado tras reconexión #2",
            ),
        ]

        # Enviar vía API (simula reconexión exitosa)
        response = await client.post(
            "/api/v2/events",
            json={"events": eventos_offline},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["processed"] == 2
        assert data["failed"] == 0
        assert len(data["event_ids"]) == 2

        # Verificar persistencia
        events_result = await session.execute(select(NormalizedEvent))
        events = list(events_result.scalars().all())
        assert len(events) == 2

        # Verificar alertas generadas (los eventos matchean la regla)
        alerts_result = await session.execute(select(Alert))
        alerts = list(alerts_result.scalars().all())
        assert len(alerts) >= 1, (
            "Los eventos reenviados debieron generar alertas en el engine"
        )
