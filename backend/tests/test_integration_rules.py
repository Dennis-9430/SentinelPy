"""Tests de integración para RuleService con PostgreSQL real.

Verifica CRUD completo de reglas de detección, paginación,
filtros, y carga de reglas activas contra base de datos real.
"""

import pytest
from uuid import UUID

from app.services.rule_service import RuleService
from app.models.rule import DetectionRule


# ── Helpers ────────────────────────────────────────────────────────────────

def _regla_base() -> dict:
    """Retorna un dict con campos mínimos de una regla."""
    return {
        "title": "Intento de login como root",
        "description": "Detecta cuando alguien intenta loguearse como root",
        "severity": "high",
        "status": "active",
        "conditions": {
            "operator": "AND",
            "conditions": [
                {"field": "event_type", "operator": "eq", "value": "authentication"},
                {"field": "user_name", "operator": "eq", "value": "root"},
            ],
        },
        "alert_title": "Login root detectado",
        "alert_severity": "high",
        "correlation_window": 300,
        "author": "test",
        "tags": ["attack.t1078"],
        "references": [],
        "false_positives": "Entorno de desarrollo",
    }


# ── Tests ──────────────────────────────────────────────────────────────────

class TestCrearRegla:
    """Prueba la creación de reglas en PostgreSQL real."""

    @pytest.mark.asyncio
    async def test_crear_regla_simple(self, session):
        """Crea una regla y verifica persistencia."""
        service = RuleService(session)
        datos = _regla_base()

        regla = await service.crear_regla(datos)

        assert regla.id is not None
        assert isinstance(regla.id, UUID)
        assert regla.title == "Intento de login como root"
        assert regla.severity == "high"
        assert regla.status == "active"
        assert regla.created_at is not None
        assert regla.updated_at is not None

    @pytest.mark.asyncio
    async def test_crear_regla_con_conditions_json(self, session):
        """Verifica que el campo JSON conditions se guarde y recupere."""
        service = RuleService(session)
        datos = _regla_base()

        regla = await service.crear_regla(datos)

        assert regla.conditions["operator"] == "AND"
        assert len(regla.conditions["conditions"]) == 2
        assert regla.conditions["conditions"][0]["field"] == "event_type"

    @pytest.mark.asyncio
    async def test_crear_regla_sin_campos_opcionales(self, session):
        """Crea regla con solo campos obligatorios."""
        service = RuleService(session)
        datos = {
            "title": "Regla mínima",
            "description": "Descripción",
            "conditions": {"operator": "AND", "conditions": []},
            "alert_title": "Alerta mínima",
        }

        regla = await service.crear_regla(datos)

        assert regla.id is not None
        assert regla.severity == "medium"  # default
        assert regla.status == "active"  # default


class TestListarReglas:
    """Prueba listado, paginación y filtros de reglas."""

    @pytest.mark.asyncio
    async def test_listar_vacio(self, session):
        """Sin reglas, listar devuelve lista vacía."""
        service = RuleService(session)
        reglas, total = await service.listar_reglas()

        assert reglas == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_listar_con_datos(self, session):
        """Con reglas creadas, listar devuelve todas."""
        service = RuleService(session)
        for i in range(3):
            datos = _regla_base()
            datos["title"] = f"Regla {i}"
            await service.crear_regla(datos)

        reglas, total = await service.listar_reglas()

        assert total == 3
        assert len(reglas) == 3

    @pytest.mark.asyncio
    async def test_filtro_por_estado(self, session):
        """Filtrar por status devuelve solo reglas en ese estado."""
        service = RuleService(session)
        datos_activa = _regla_base()
        await service.crear_regla(datos_activa)

        datos_disabled = _regla_base()
        datos_disabled["title"] = "Regla desactivada"
        datos_disabled["status"] = "disabled"
        await service.crear_regla(datos_disabled)

        reglas, total = await service.listar_reglas(estado="active")

        assert total == 1
        assert reglas[0].status == "active"

    @pytest.mark.asyncio
    async def test_filtro_por_severidad(self, session):
        """Filtrar por severidad devuelve solo reglas de esa severidad."""
        service = RuleService(session)
        datos_alta = _regla_base()
        await service.crear_regla(datos_alta)

        datos_media = _regla_base()
        datos_media["title"] = "Regla media"
        datos_media["severity"] = "medium"
        await service.crear_regla(datos_media)

        reglas, total = await service.listar_reglas(severidad="high")

        assert total == 1
        assert reglas[0].severity == "high"


class TestObtenerRegla:
    """Prueba obtener regla por ID."""

    @pytest.mark.asyncio
    async def test_obtener_regla_existente(self, session):
        """Obtener regla por UUID existente devuelve la regla."""
        service = RuleService(session)
        creada = await service.crear_regla(_regla_base())

        obtenida = await service.obtener_regla(str(creada.id))

        assert obtenida is not None
        assert obtenida.id == creada.id
        assert obtenida.title == "Intento de login como root"

    @pytest.mark.asyncio
    async def test_obtener_regla_inexistente(self, session):
        """Obtener regla con UUID inexistente devuelve None."""
        service = RuleService(session)
        obtenida = await service.obtener_regla("00000000-0000-0000-0000-000000000000")

        assert obtenida is None

    @pytest.mark.asyncio
    async def test_obtener_regla_id_invalido(self, session):
        """Obtener regla con string no-UUID devuelve None sin crash."""
        service = RuleService(session)
        obtenida = await service.obtener_regla("no-soy-un-uuid")

        assert obtenida is None


class TestActualizarRegla:
    """Prueba actualización de reglas."""

    @pytest.mark.asyncio
    async def test_actualizar_campos(self, session):
        """Actualizar título y severidad de una regla."""
        service = RuleService(session)
        creada = await service.crear_regla(_regla_base())

        actualizada = await service.actualizar_regla(
            str(creada.id),
            {"title": "Nuevo título", "severity": "critical"},
        )

        assert actualizada is not None
        assert actualizada.title == "Nuevo título"
        assert actualizada.severity == "critical"
        # updated_at puede ser igual si la actualización ocurre en el mismo microsegundo
        assert actualizada.updated_at >= creada.updated_at

    @pytest.mark.asyncio
    async def test_actualizar_inexistente(self, session):
        """Actualizar regla que no existe devuelve None."""
        service = RuleService(session)
        result = await service.actualizar_regla(
            "00000000-0000-0000-0000-000000000000",
            {"title": "No importa"},
        )

        assert result is None


class TestEliminarRegla:
    """Prueba eliminación de reglas."""

    @pytest.mark.asyncio
    async def test_eliminar_regla_existente(self, session):
        """Eliminar regla existente devuelve True."""
        service = RuleService(session)
        creada = await service.crear_regla(_regla_base())

        eliminado = await service.eliminar_regla(str(creada.id))

        assert eliminado is True

        # Verificar que ya no existe
        obtenida = await service.obtener_regla(str(creada.id))
        assert obtenida is None

    @pytest.mark.asyncio
    async def test_eliminar_regla_inexistente(self, session):
        """Eliminar regla que no existe devuelve False."""
        service = RuleService(session)
        eliminado = await service.eliminar_regla(
            "00000000-0000-0000-0000-000000000000"
        )

        assert eliminado is False


class TestReglasActivas:
    """Prueba carga de reglas activas para el motor de correlación."""

    @pytest.mark.asyncio
    async def test_cargar_reglas_activas(self, session):
        """Cargar reglas activas devuelve solo las activas."""
        service = RuleService(session)
        await service.crear_regla(_regla_base())  # activa

        datos_disabled = _regla_base()
        datos_disabled["title"] = "Desactivada"
        datos_disabled["status"] = "disabled"
        await service.crear_regla(datos_disabled)

        datos_test = _regla_base()
        datos_test["title"] = "En test"
        datos_test["status"] = "test"
        await service.crear_regla(datos_test)

        activas = await service.cargar_reglas_activas()

        assert len(activas) == 1
        assert activas[0].status == "active"
        assert activas[0].title == "Intento de login como root"

    @pytest.mark.asyncio
    async def test_cargar_reglas_activas_sin_datos(self, session):
        """Sin reglas activas, cargar devuelve lista vacía."""
        service = RuleService(session)
        datos = _regla_base()
        datos["status"] = "disabled"
        await service.crear_regla(datos)

        activas = await service.cargar_reglas_activas()

        assert activas == []
