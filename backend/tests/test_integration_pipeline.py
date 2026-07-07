"""Tests de integración para Pipeline con PostgreSQL real.

Verifica que el pipeline procese logs crudos, los persista en
PostgreSQL, y (opcionalmente) evalúe reglas de correlación.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.event import NormalizedEvent
from app.services.engine import CorrelationEngine
from app.services.pipeline import Pipeline
from app.services.rule_service import RuleService

# ── Helper ─────────────────────────────────────────────────────────────────


def _pipeline_factory(async_engine, engine=None):
    """Crea un Pipeline con session_factory apuntando al testcontainer."""
    factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    return Pipeline(engine=engine, session_factory=factory)


# ── Tests ──────────────────────────────────────────────────────────────────


class TestPipelinePersistencia:
    """Prueba que Pipeline procese y persista eventos correctamente."""

    @pytest.mark.asyncio
    async def test_procesar_log_json(self, session, async_engine):
        """Pipeline procesa un JSON y lo persiste en DB."""
        pipeline = _pipeline_factory(async_engine)
        log_json = (
            '{"event_type": "auth_failure", "severity": "high", '
            '"description": "Fallo de autenticación", '
            '"source": "web-01", "collector_type": "test", '
            '"event_timestamp": "2024-01-01T00:00:00Z"}'
        )

        evento = await pipeline.process(log_json)

        assert evento is not None
        assert evento.event_type == "auth_failure"
        assert evento.severity == "high"

        # Verificar que está persistido
        result = await session.execute(select(func.count(NormalizedEvent.id)))
        total = result.scalar() or 0
        assert total >= 1

    @pytest.mark.asyncio
    async def test_procesar_log_syslog(self, session, async_engine):
        """Pipeline procesa un syslog RFC 3164 y lo persiste."""
        pipeline = _pipeline_factory(async_engine)
        log_syslog = (
            "<34>Oct 11 22:14:15 mymachine.example.com "
            "sshd[1234]: Failed password for root from 10.0.0.1 port 22"
        )

        evento = await pipeline.process(log_syslog)

        assert evento is not None
        # syslog parser usa 'syslog' como collector_type default
        assert evento.collector_type == "syslog"

    @pytest.mark.asyncio
    async def test_procesar_log_invalido(self, async_engine):
        """Log inválido devuelve None sin crash."""
        pipeline = _pipeline_factory(async_engine)
        evento = await pipeline.process("")
        assert evento is None

        evento = await pipeline.process(None)
        assert evento is None

    @pytest.mark.asyncio
    async def test_procesar_log_sin_origen(self, async_engine):
        """Log sin información de origen se procesa igual."""
        pipeline = _pipeline_factory(async_engine)
        log_json = (
            '{"event_type": "test", "severity": "low", '
            '"description": "Sin origen", '
            '"collector_type": "test", '
            '"event_timestamp": "2024-01-01T00:00:00Z"}'
        )

        evento = await pipeline.process(log_json)

        assert evento is not None
        # "unknown" es el default cuando no hay source ni origen
        assert evento.source == "unknown"

    @pytest.mark.asyncio
    async def test_procesar_con_origen(self, async_engine):
        """Log con origen (host, port) se refleja en el campo source."""
        pipeline = _pipeline_factory(async_engine)
        log_json = (
            '{"event_type": "test", "severity": "low", '
            '"description": "Con origen", '
            '"collector_type": "test", '
            '"event_timestamp": "2024-01-01T00:00:00Z"}'
        )

        evento = await pipeline.process(log_json, origen=("10.0.0.1", 5140))

        assert evento is not None
        assert evento.source == "10.0.0.1:5140"


class TestPipelineConEngine:
    """Prueba Pipeline con CorrelationEngine integrado."""

    @pytest.mark.asyncio
    async def test_engine_evalua_regla_y_crea_alerta(self, session, async_engine):
        """Pipeline + Engine: evento que matchea regla activa genera alerta."""
        from app.models.alert import Alert

        # Crear regla activa
        rule_service = RuleService(session)
        regla = await rule_service.crear_regla(
            {
                "title": "Detectar auth_failure",
                "description": "Regla para test",
                "severity": "high",
                "status": "active",
                "conditions": {
                    "operator": "AND",
                    "conditions": [
                        {
                            "field": "event_type",
                            "operator": "eq",
                            "value": "auth_failure",
                        },
                    ],
                },
                "alert_title": "Auth Failure Detectado",
                "alert_severity": "high",
                "correlation_window": 300,
            }
        )

        # Engine con callback que persiste alertas
        engine = CorrelationEngine()
        alertas_creadas = []

        async def callback(datos_alerta):
            async with async_sessionmaker(
                session.bind, class_=AsyncSession, expire_on_commit=False
            )() as ses:
                alerta = Alert(**datos_alerta)
                ses.add(alerta)
                await ses.commit()
                await ses.refresh(alerta)
                alertas_creadas.append(alerta)
            return alertas_creadas[-1]

        engine.registrar_callback(callback)
        engine.cargar_reglas([regla])

        pipeline = _pipeline_factory(async_engine, engine=engine)
        log_json = (
            '{"event_type": "auth_failure", "severity": "high", '
            '"description": "Fallo de autenticación detectado", '
            '"source": "web-01", "collector_type": "test", '
            '"event_timestamp": "2024-01-01T00:00:00Z"}'
        )

        evento = await pipeline.process(log_json)

        assert evento is not None
        assert len(alertas_creadas) >= 1
        assert alertas_creadas[0].title == "Auth Failure Detectado"
        assert alertas_creadas[0].severity == "high"

    @pytest.mark.asyncio
    async def test_engine_no_genera_alerta_si_no_matchea(self, session, async_engine):
        """Evento que no matchea ninguna regla no genera alerta."""
        from app.models.alert import Alert

        rule_service = RuleService(session)
        regla = await rule_service.crear_regla(
            {
                "title": "Detectar solo port_scan",
                "description": "Regla para test",
                "severity": "high",
                "status": "active",
                "conditions": {
                    "operator": "AND",
                    "conditions": [
                        {"field": "event_type", "operator": "eq", "value": "port_scan"},
                    ],
                },
                "alert_title": "Port Scan Detectado",
                "alert_severity": "high",
            }
        )

        engine = CorrelationEngine()
        alertas_creadas = []

        async def callback(datos_alerta):
            async with async_sessionmaker(
                session.bind, class_=AsyncSession, expire_on_commit=False
            )() as ses:
                alerta = Alert(**datos_alerta)
                ses.add(alerta)
                await ses.commit()
                await ses.refresh(alerta)
                alertas_creadas.append(alerta)

        engine.registrar_callback(callback)
        engine.cargar_reglas([regla])

        pipeline = _pipeline_factory(async_engine, engine=engine)
        log_json = (
            '{"event_type": "auth_failure", "severity": "low", '
            '"description": "Esto no matchea", '
            '"source": "web-01", "collector_type": "test", '
            '"event_timestamp": "2024-01-01T00:00:00Z"}'
        )

        evento = await pipeline.process(log_json)

        assert evento is not None
        assert len(alertas_creadas) == 0
