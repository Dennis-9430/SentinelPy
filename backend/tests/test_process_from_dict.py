"""Tests unitarios para Pipeline.process_from_dict().

Verifica que el método:
1. Persista el evento a través de _guardar_evento
2. Evalúe el engine si hay reglas activas que matcheen
3. No falle si engine.evaluate() lanza excepción
4. Aplique collector_type override
5. Use "unknown" como source default
"""

import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone

from app.services.pipeline import Pipeline
from app.services.engine import CorrelationEngine


class FakeEvent:
    """Evento simulado para evitar dependencia de BD en tests unitarios."""
    id = "550e8400-e29b-41d4-a716-446655440000"
    source = "test-server"
    collector_type = "rest"
    event_timestamp = datetime.now(timezone.utc)
    event_type = "test_event"
    severity = "low"
    description = "Evento de test unitario"
    source_ip = None
    destination_ip = None
    source_port = None
    destination_port = None
    protocol = None
    user_name = None
    process_name = None
    file_path = None


def _pipeline_con_engine_mock() -> tuple[Pipeline, CorrelationEngine, list]:
    """Crea Pipeline con engine y mock de _guardar_evento.

    Retorna:
        (pipeline, engine, alertas_creadas) para assertions.
    """
    engine = CorrelationEngine()
    alertas_creadas = []

    async def spy_callback(datos_alerta):
        alertas_creadas.append(datos_alerta)

    engine.registrar_callback(spy_callback)
    engine.cargar_reglas([{
        "id": "test-rule-1",
        "title": "Detectar test_event",
        "alert_title": "Test Alert from Pipeline",
        "alert_severity": "medium",
        "event_type": "test_event",
        "severity": "low",
        "conditions": {"field": "event_type", "operator": "eq", "value": "test_event"},
        "status": "active",
    }])

    pipeline = Pipeline(engine=engine)
    # Mockear _guardar_evento para evitar DB
    pipeline._guardar_evento = AsyncMock(return_value=FakeEvent())

    return pipeline, engine, alertas_creadas


class TestProcessFromDict:
    """Prueba el comportamiento de Pipeline.process_from_dict()."""

    @pytest.mark.asyncio
    async def test_ejecuta_engine_y_callback(self):
        """process_from_dict ejecuta engine.evaluate() y dispara callback."""
        pipeline, _, alertas = _pipeline_con_engine_mock()

        evento_dict = {
            "source": "test-server",
            "collector_type": "rest",
            "event_timestamp": datetime.now(timezone.utc),
            "event_type": "test_event",
            "severity": "low",
            "description": "Evento que debe matchear regla",
        }

        evento = await pipeline.process_from_dict(evento_dict)

        assert evento is not None
        # Verificar que el callback se ejecutó (engine.evaluate() llamó a _crear_alerta)
        assert len(alertas) >= 1
        assert alertas[0]["title"] == "Test Alert from Pipeline"
        assert alertas[0]["rule_id"] == "test-rule-1"

    @pytest.mark.asyncio
    async def test_sin_engine_no_falla(self):
        """process_from_dict sin engine configurado no falla, solo persiste."""
        pipeline = Pipeline(engine=None)
        pipeline._guardar_evento = AsyncMock(return_value=FakeEvent())

        evento_dict = {
            "source": "test-server",
            "collector_type": "rest",
            "event_timestamp": datetime.now(timezone.utc),
            "event_type": "test_event",
            "severity": "low",
            "description": "Evento sin engine",
        }

        evento = await pipeline.process_from_dict(evento_dict)

        assert evento is not None
        assert evento.event_type == "test_event"

    @pytest.mark.asyncio
    async def test_override_collector_type(self):
        """process_from_dict sobreescribe collector_type si se provee."""
        pipeline = Pipeline(engine=None)
        pipeline._guardar_evento = AsyncMock(return_value=FakeEvent())

        evento_dict = {
            "source": "test-server",
            "collector_type": "original",
            "event_timestamp": datetime.now(timezone.utc),
            "event_type": "test_event",
            "severity": "low",
            "description": "Test collector_type override",
        }

        # Verificar que el dict fue modificado ANTES de _guardar_evento
        original_guardar = pipeline._guardar_evento

        async def assert_guardar(datos):
            assert datos["collector_type"] == "rest", \
                f"Expected 'rest', got '{datos.get('collector_type')}'"
            return FakeEvent()

        pipeline._guardar_evento = assert_guardar

        await pipeline.process_from_dict(evento_dict, collector_type="rest")

    @pytest.mark.asyncio
    async def test_source_default_unknown(self):
        """Si no hay source, process_from_dict usa 'unknown'."""
        pipeline = Pipeline(engine=None)
        pipeline._guardar_evento = AsyncMock(return_value=FakeEvent())

        async def assert_guardar(datos):
            assert datos["source"] == "unknown", \
                f"Expected 'unknown', got '{datos.get('source')}'"
            return FakeEvent()

        pipeline._guardar_evento = assert_guardar

        evento_dict = {
            "collector_type": "rest",
            "event_timestamp": datetime.now(timezone.utc),
            "event_type": "test_event",
            "severity": "low",
            "description": "Sin source explícito",
        }

        await pipeline.process_from_dict(evento_dict)

    @pytest.mark.asyncio
    async def test_error_engine_no_propaga(self):
        """Si engine.evaluate() falla, el error se loggea pero no se propaga."""
        pipeline, engine, _ = _pipeline_con_engine_mock()

        # Hacer que engine.evaluate() falle
        engine.evaluate = AsyncMock(side_effect=ValueError("Engine crash!"))

        evento_dict = {
            "source": "test-server",
            "collector_type": "rest",
            "event_timestamp": datetime.now(timezone.utc),
            "event_type": "test_event",
            "severity": "low",
            "description": "Evento que causa error en engine",
        }

        # No debe propagar la excepción
        evento = await pipeline.process_from_dict(evento_dict)
        assert evento is not None
