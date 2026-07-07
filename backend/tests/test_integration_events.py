"""Tests de integración para EventService con PostgreSQL real.

Verifica que las operaciones CRUD, paginación, filtros y estadísticas
funcionen correctamente contra una base de datos real (Testcontainers).
"""

from datetime import UTC, datetime

import pytest

from app.services.event_service import EventService
from app.services.pipeline import Pipeline
from app.services.rule_service import RuleService

# ── Helpers ────────────────────────────────────────────────────────────────


def _evento_base() -> dict:
    """Retorna un dict con los campos mínimos de un evento normalizado."""
    return {
        "source": "test-server-01",
        "collector_type": "test",
        "event_timestamp": datetime.now(UTC),
        "event_type": "test_event",
        "severity": "low",
        "description": "Evento de test",
    }


# ── Tests ──────────────────────────────────────────────────────────────────


class TestCrearEvento:
    """Prueba la creación de eventos en PostgreSQL real."""

    @pytest.mark.asyncio
    async def test_crear_evento_simple(self, session):
        """Crea un evento y verifica que se persista con ID y timestamps."""
        service = EventService(session)
        datos = _evento_base()

        evento = await service.crear_evento(datos)

        assert evento.id is not None
        assert evento.source == "test-server-01"
        assert evento.event_type == "test_event"
        assert evento.severity == "low"
        assert evento.created_at is not None
        assert evento.updated_at is not None

    @pytest.mark.asyncio
    async def test_crear_evento_con_todos_los_campos(self, session):
        """Crea un evento con todos los campos opcionales."""
        service = EventService(session)
        ahora = datetime.now(UTC)
        datos = {
            "source": "firewall-01",
            "collector_type": "syslog",
            "event_timestamp": ahora,
            "event_type": "port_scan",
            "severity": "high",
            "description": "Escaneo de puertos detectado desde 10.0.0.1",
            "source_ip": "10.0.0.1",
            "destination_ip": "192.168.1.100",
            "source_port": 54321,
            "destination_port": 22,
            "protocol": "TCP",
            "user_name": "root",
            "process_name": "sshd",
            "file_path": "/var/log/auth.log",
        }

        evento = await service.crear_evento(datos)

        assert evento.source_ip == "10.0.0.1"
        assert evento.destination_port == 22
        assert evento.protocol == "TCP"
        assert evento.user_name == "root"


class TestListarEventos:
    """Prueba paginación y filtros de eventos."""

    @pytest.mark.asyncio
    async def test_listar_eventos_vacio(self, session):
        """Sin eventos, listar devuelve lista vacía y total 0."""
        service = EventService(session)
        eventos, total = await service.listar_eventos()

        assert eventos == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_listar_eventos_con_datos(self, session):
        """Con eventos creados, listar devuelve los eventos y el total."""
        service = EventService(session)
        for i in range(5):
            datos = _evento_base()
            datos["description"] = f"Evento {i}"
            await service.crear_evento(datos)

        eventos, total = await service.listar_eventos(limite=10)

        assert total == 5
        assert len(eventos) == 5

    @pytest.mark.asyncio
    async def test_listar_eventos_paginacion(self, session):
        """Verifica que limite y offset funcionen correctamente."""
        service = EventService(session)
        for i in range(10):
            datos = _evento_base()
            datos["description"] = f"Evento {i}"
            await service.crear_evento(datos)

        eventos_pagina, total = await service.listar_eventos(limite=3, desde=0)
        assert len(eventos_pagina) == 3
        assert total == 10

        eventos_pagina2, _ = await service.listar_eventos(limite=3, desde=3)
        assert len(eventos_pagina2) == 3
        # Verificar que son eventos distintos (paginación real)
        assert eventos_pagina[0].id != eventos_pagina2[0].id

    @pytest.mark.asyncio
    async def test_filtro_por_tipo(self, session):
        """Filtrar por event_type devuelve solo eventos de ese tipo."""
        service = EventService(session)
        for tipo in ["auth_failure", "port_scan", "auth_failure"]:
            datos = _evento_base()
            datos["event_type"] = tipo
            await service.crear_evento(datos)

        eventos, total = await service.listar_eventos(tipo="auth_failure")

        assert total == 2
        assert all(e.event_type == "auth_failure" for e in eventos)

    @pytest.mark.asyncio
    async def test_filtro_por_severidad(self, session):
        """Filtrar por severidad devuelve solo eventos de esa severidad."""
        service = EventService(session)
        datos_alta = _evento_base()
        datos_alta["severity"] = "high"
        await service.crear_evento(datos_alta)

        datos_baja = _evento_base()
        datos_baja["severity"] = "low"
        await service.crear_evento(datos_baja)

        eventos, total = await service.listar_eventos(severidad="high")

        assert total == 1
        assert eventos[0].severity == "high"

    @pytest.mark.asyncio
    async def test_filtros_combinados(self, session):
        """Filtros de tipo y severidad combinados."""
        service = EventService(session)
        for tipo, sev in [
            ("auth_failure", "high"),
            ("auth_failure", "low"),
            ("port_scan", "high"),
        ]:
            datos = _evento_base()
            datos["event_type"] = tipo
            datos["severity"] = sev
            await service.crear_evento(datos)

        eventos, total = await service.listar_eventos(
            tipo="auth_failure", severidad="high"
        )

        assert total == 1
        assert eventos[0].event_type == "auth_failure"
        assert eventos[0].severity == "high"


class TestEstadisticas:
    """Prueba el endpoint de estadísticas de eventos."""

    @pytest.mark.asyncio
    async def test_estadisticas_sin_datos(self, session):
        """Sin eventos, las estadísticas devuelven ceros."""
        service = EventService(session)
        stats = await service.obtener_estadisticas()

        assert stats["total_eventos"] == 0
        assert stats["eventos_ultima_hora"] == 0

    @pytest.mark.asyncio
    async def test_estadisticas_con_datos(self, session):
        """Con eventos, las estadísticas reflejan los totales."""
        service = EventService(session)
        for _ in range(3):
            await service.crear_evento(_evento_base())

        stats = await service.obtener_estadisticas()

        assert stats["total_eventos"] == 3
        assert stats["eventos_ultima_hora"] == 3  # Todos son recientes


class TestPipelineEngineIntegration:
    """Prueba que POST /api/events ejecute engine.evaluate() vía pipeline.

    Verifica que cuando un evento se crea a través del pipeline, el motor
    de correlación evalúa el evento y los callbacks de alerta se ejecutan.
    """

    @pytest.mark.asyncio
    async def test_process_from_dict_ejecuta_engine_y_callback(
        self, session, async_engine
    ):
        """process_from_dict con engine + regla activa ejecuta callback de alerta."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from app.services.engine import CorrelationEngine

        # Crear regla activa en DB
        rule_service = RuleService(session)
        regla = await rule_service.crear_regla(
            {
                "title": "Regla Pipeline Events",
                "description": "Regla para test de integración events",
                "severity": "high",
                "status": "active",
                "conditions": {
                    "operator": "AND",
                    "conditions": [
                        {
                            "field": "event_type",
                            "operator": "eq",
                            "value": "test_event",
                        },
                    ],
                },
                "alert_title": "Pipeline Events Alert",
                "alert_severity": "medium",
                "correlation_window": 300,
            }
        )

        # Engine con callback spy
        engine = CorrelationEngine()
        callback_called = False
        alerta_recibida = None

        async def spy_callback(datos_alerta):
            nonlocal callback_called, alerta_recibida
            callback_called = True
            alerta_recibida = datos_alerta

        engine.registrar_callback(spy_callback)
        engine.cargar_reglas([regla])

        # Pipeline con session_factory apuntando al testcontainer
        factory = async_sessionmaker(
            async_engine, class_=AsyncSession, expire_on_commit=False
        )
        pipeline = Pipeline(engine=engine, session_factory=factory)

        # Act: llamar process_from_dict con datos que matchean la regla
        evento_dict = {
            "source": "test-server-events",
            "collector_type": "rest",
            "event_timestamp": datetime.now(UTC),
            "event_type": "test_event",
            "severity": "low",
            "description": "Evento de test para pipeline+engine",
        }

        evento = await pipeline.process_from_dict(evento_dict)

        # Assert
        assert evento is not None
        assert evento.id is not None
        assert evento.event_type == "test_event"
        assert callback_called, (
            "El callback de alerta del engine NO se ejecutó — "
            "engine.evaluate() no fue llamado o no matcheó la regla"
        )
        assert alerta_recibida is not None
        assert alerta_recibida["title"] == "Pipeline Events Alert"

    @pytest.mark.asyncio
    async def test_process_from_dict_sin_engine_no_callback(self, async_engine):
        """Sin engine, process_from_dict no ejecuta callback."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(
            async_engine, class_=AsyncSession, expire_on_commit=False
        )
        pipeline = Pipeline(engine=None, session_factory=factory)

        evento_dict = {
            "source": "test-server-no-engine",
            "collector_type": "rest",
            "event_timestamp": datetime.now(UTC),
            "event_type": "test_event",
            "severity": "low",
            "description": "Evento sin engine",
        }

        evento = await pipeline.process_from_dict(evento_dict)

        assert evento is not None
        assert evento.id is not None
