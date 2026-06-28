"""Tests de integración para AlertService con PostgreSQL real.

Verifica CRUD de alertas, ciclo de vida (cambios de estado),
y actualización de contadores de ventana temporal.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID

from app.services.alert_service import AlertService
from app.services.rule_service import RuleService
from app.models.alert import Alert


# ── Helpers ────────────────────────────────────────────────────────────────

def _regla_base() -> dict:
    """Retorna datos mínimos de una regla para crear alertas vinculadas."""
    return {
        "title": "Regla de prueba",
        "description": "Regla para tests de integración",
        "severity": "high",
        "status": "active",
        "conditions": {
            "operator": "AND",
            "conditions": [
                {"field": "event_type", "operator": "eq", "value": "test"},
            ],
        },
        "alert_title": "Alerta de prueba",
        "alert_severity": "high",
        "correlation_window": 300,
    }


def _alerta_base(rule_id: UUID) -> dict:
    """Retorna datos mínimos de una alerta vinculada a una regla."""
    return {
        "rule_id": rule_id,
        "title": "Alerta de prueba",
        "severity": "high",
        "description": "Alerta generada por test de integración",
        "status": "open",
        "event_count": 1,
    }


# ── Fixture ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def rule_id(session) -> UUID:
    """Crea una regla y retorna su ID para usar en alertas."""
    service = RuleService(session)
    regla = await service.crear_regla(_regla_base())
    return regla.id


# ── Tests ──────────────────────────────────────────────────────────────────

class TestCrearAlerta:
    """Prueba la creación de alertas vinculadas a reglas."""

    @pytest.mark.asyncio
    async def test_crear_alerta_simple(self, session, rule_id):
        """Crea alerta y verifica persistencia con regla asociada."""
        service = AlertService(session)
        datos = _alerta_base(rule_id)

        alerta = await service.crear_alerta(datos)

        assert alerta.id is not None
        assert isinstance(alerta.id, UUID)
        assert alerta.rule_id == rule_id
        assert alerta.title == "Alerta de prueba"
        assert alerta.severity == "high"
        assert alerta.status == "open"
        assert alerta.event_count == 1
        assert alerta.created_at is not None

    @pytest.mark.asyncio
    async def test_crear_alerta_con_campos_opcionales(self, session, rule_id):
        """Crea alerta con campos de ventana temporal."""
        ahora = datetime.now(timezone.utc)
        service = AlertService(session)
        datos = _alerta_base(rule_id)
        datos["first_event_at"] = ahora
        datos["last_event_at"] = ahora
        datos["event_count"] = 5

        alerta = await service.crear_alerta(datos)

        assert alerta.event_count == 5
        assert alerta.first_event_at is not None
        assert alerta.last_event_at is not None


class TestListarAlertas:
    """Prueba listado, paginación y filtros de alertas."""

    @pytest.mark.asyncio
    async def test_listar_vacio(self, session):
        """Sin alertas, listar devuelve lista vacía."""
        service = AlertService(session)
        alertas, total = await service.listar_alertas()

        assert alertas == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_listar_con_datos(self, session, rule_id):
        """Con alertas creadas, listar devuelve todas."""
        service = AlertService(session)
        for i in range(3):
            datos = _alerta_base(rule_id)
            datos["title"] = f"Alerta {i}"
            await service.crear_alerta(datos)

        alertas, total = await service.listar_alertas()

        assert total == 3
        assert len(alertas) == 3

    @pytest.mark.asyncio
    async def test_filtro_por_estado(self, session, rule_id):
        """Filtrar por estado devuelve solo alertas en ese estado."""
        service = AlertService(session)
        datos_open = _alerta_base(rule_id)
        await service.crear_alerta(datos_open)

        datos_resolved = _alerta_base(rule_id)
        datos_resolved["title"] = "Resuelta"
        datos_resolved["status"] = "resolved"
        await service.crear_alerta(datos_resolved)

        alertas, total = await service.listar_alertas(estado="open")

        assert total == 1
        assert alertas[0].status == "open"

    @pytest.mark.asyncio
    async def test_filtro_por_severidad(self, session, rule_id):
        """Filtrar por severidad devuelve solo alertas de esa severidad."""
        service = AlertService(session)
        datos_alta = _alerta_base(rule_id)
        await service.crear_alerta(datos_alta)

        datos_media = _alerta_base(rule_id)
        datos_media["title"] = "Alerta media"
        datos_media["severity"] = "medium"
        await service.crear_alerta(datos_media)

        alertas, total = await service.listar_alertas(severidad="high")

        assert total == 1
        assert alertas[0].severity == "high"


class TestCicloDeVida:
    """Prueba el ciclo de vida de alertas (cambios de estado)."""

    @pytest.mark.asyncio
    async def test_actualizar_estado(self, session, rule_id):
        """Cambiar estado de open a acknowledged."""
        service = AlertService(session)
        alerta = await service.crear_alerta(_alerta_base(rule_id))

        actualizada = await service.actualizar_estado(
            str(alerta.id), "acknowledged"
        )

        assert actualizada is not None
        assert actualizada.status == "acknowledged"

    @pytest.mark.asyncio
    async def test_resolver_con_notas(self, session, rule_id):
        """Resolver alerta con notas debe setear resolved_at."""
        service = AlertService(session)
        alerta = await service.crear_alerta(_alerta_base(rule_id))

        actualizada = await service.actualizar_estado(
            str(alerta.id), "resolved", notas="Falso positivo - tráfico esperado"
        )

        assert actualizada.status == "resolved"
        assert actualizada.resolved_at is not None
        assert actualizada.resolution_notes == "Falso positivo - tráfico esperado"

    @pytest.mark.asyncio
    async def test_false_positive(self, session, rule_id):
        """Marcar como false_positive también setea resolved_at."""
        service = AlertService(session)
        alerta = await service.crear_alerta(_alerta_base(rule_id))

        actualizada = await service.actualizar_estado(
            str(alerta.id), "false_positive"
        )

        assert actualizada.status == "false_positive"
        assert actualizada.resolved_at is not None

    @pytest.mark.asyncio
    async def test_actualizar_estado_inexistente(self, session):
        """Cambiar estado de alerta inexistente devuelve None."""
        service = AlertService(session)
        result = await service.actualizar_estado(
            "00000000-0000-0000-0000-000000000000", "resolved"
        )

        assert result is None


class TestActualizarContadores:
    """Prueba actualización de contadores de ventana temporal."""

    @pytest.mark.asyncio
    async def test_actualizar_contadores_alerta_abierta(self, session, rule_id):
        """Actualiza event_count y last_event_at en alerta open."""
        service = AlertService(session)
        alerta = await service.crear_alerta(_alerta_base(rule_id))

        ahora = datetime.now(timezone.utc)
        actualizada = await service.actualizar_contadores(
            str(rule_id), event_count=5, last_event_at=ahora
        )

        assert actualizada is not None
        assert actualizada.event_count == 5
        assert actualizada.last_event_at == ahora

    @pytest.mark.asyncio
    async def test_actualizar_contadores_sin_alerta_abierta(self, session, rule_id):
        """Sin alerta abierta para la regla, actualizar devuelve None."""
        service = AlertService(session)
        alerta = await service.crear_alerta(_alerta_base(rule_id))

        # Resolver la alerta
        await service.actualizar_estado(str(alerta.id), "resolved")

        ahora = datetime.now(timezone.utc)
        result = await service.actualizar_contadores(
            str(rule_id), event_count=5, last_event_at=ahora
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_actualizar_contadores_varias_veces(self, session, rule_id):
        """Múltiples actualizaciones incrementan el contador."""
        service = AlertService(session)
        await service.crear_alerta(_alerta_base(rule_id))

        ahora = datetime.now(timezone.utc)
        for count in [2, 3, 7]:
            actualizada = await service.actualizar_contadores(
                str(rule_id), event_count=count, last_event_at=ahora
            )
            assert actualizada.event_count == count

    @pytest.mark.asyncio
    async def test_actualizar_contadores_rule_id_invalido(self, session):
        """UUID inválido no causa crash."""
        service = AlertService(session)
        result = await service.actualizar_contadores(
            "no-soy-uuid", event_count=1, last_event_at=datetime.now(timezone.utc)
        )
        assert result is None


class TestEstadisticasAlertas:
    """Prueba estadísticas de alertas."""

    @pytest.mark.asyncio
    async def test_estadisticas_sin_datos(self, session):
        """Sin alertas, stats devuelven ceros."""
        service = AlertService(session)
        stats = await service.obtener_estadisticas()

        assert stats["total_alertas"] == 0
        assert stats["alertas_abiertas"] == 0
        assert stats["alertas_resueltas"] == 0

    @pytest.mark.asyncio
    async def test_estadisticas_con_mix_estados(self, session, rule_id):
        """Stats reflejan correctamente alertas abiertas vs resueltas."""
        service = AlertService(session)
        # 2 abiertas
        await service.crear_alerta(_alerta_base(rule_id))
        a2 = await service.crear_alerta(_alerta_base(rule_id))
        # 1 resuelta
        a3 = await service.crear_alerta(_alerta_base(rule_id))
        await service.actualizar_estado(str(a3.id), "resolved")

        stats = await service.obtener_estadisticas()

        assert stats["total_alertas"] == 3
        assert stats["alertas_abiertas"] == 2
        assert stats["alertas_resueltas"] == 1
