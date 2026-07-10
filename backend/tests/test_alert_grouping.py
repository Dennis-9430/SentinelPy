"""Tests de integración para agrupación de alertas.

Prueba AlertService.agrupar_alertas_abiertas() con PostgreSQL real via testcontainers.
Verifica agrupación por group_key, derivación de group_name, y asignación de risk_score.
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.services.alert_service import AlertService
from app.services.rule_service import RuleService


# ── Helpers ────────────────────────────────────────────────────────────────


def _regla_base() -> dict:
    """Retorna datos mínimos de una regla para crear alertas vinculadas."""
    return {
        "title": "Brute Force Detection",
        "description": "Regla para test de agrupación",
        "severity": "high",
        "status": "active",
        "conditions": {
            "operator": "AND",
            "conditions": [
                {"field": "event_type", "operator": "eq", "value": "auth_failure"},
            ],
        },
        "alert_title": "Brute Force Alert",
        "alert_severity": "high",
        "correlation_window": 300,
    }


def _alerta_base(rule_id: UUID, **overrides) -> dict:
    """Retorna datos mínimos de una alerta vinculada a una regla."""
    data = {
        "rule_id": rule_id,
        "title": "Brute Force Alert",
        "severity": "high",
        "description": "Alerta de prueba para agrupación",
        "status": "open",
        "event_count": 1,
    }
    data.update(overrides)
    return data


async def _seed_entity_risk(session, entity_key: str, risk_score: float):
    """Crea la tabla entity_risks si no existe, y upsertea un risk_score."""
    # Ensure entity_risks table exists (created at runtime, not via Alembic)
    await session.execute(
        text(
            """CREATE TABLE IF NOT EXISTS entity_risks (
                entity_key VARCHAR(255) PRIMARY KEY,
                risk_score FLOAT NOT NULL DEFAULT 0.0,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )"""
        )
    )
    await session.execute(
        text(
            """INSERT INTO entity_risks (entity_key, risk_score, updated_at)
               VALUES (:key, :score, :ts)
               ON CONFLICT (entity_key)
               DO UPDATE SET risk_score = :score2"""
        ),
        {
            "key": entity_key,
            "score": risk_score,
            "ts": datetime.now(UTC),
            "score2": risk_score,
        },
    )
    await session.commit()


# ── Fixture ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def ensure_entity_risks(session):
    """Asegura que la tabla entity_risks existe para todos los tests."""
    await session.execute(
        text(
            """CREATE TABLE IF NOT EXISTS entity_risks (
                entity_key VARCHAR(255) PRIMARY KEY,
                risk_score FLOAT NOT NULL DEFAULT 0.0,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )"""
        )
    )
    await session.commit()


@pytest_asyncio.fixture
async def rule_id(session) -> UUID:
    """Crea una regla y retorna su ID para usar en alertas."""
    service = RuleService(session)
    regla = await service.crear_regla(_regla_base())
    return regla.id


# ── Tests ──────────────────────────────────────────────────────────────────


class TestAgruparAlertasAbiertas:
    """Prueba la agrupación de alertas abiertas por group_key."""

    @pytest.mark.asyncio
    async def test_agrupa_alertas_mismo_group_key(self, session, rule_id):
        """Alertas con el mismo group_key se agrupan y se les asigna group_name."""
        service = AlertService(session)

        # Crear 3 alertas con el mismo group_key
        for i in range(3):
            datos = _alerta_base(rule_id)
            datos["group_key"] = f"{rule_id}:192.168.1.1"
            await service.crear_alerta(datos)

        updated = await service.agrupar_alertas_abiertas()

        # Deben actualizarse las 3 alertas
        assert updated == 3

        # Verificar que se asignó group_name
        alertas, _ = await service.listar_alertas()
        for a in alertas:
            assert a.group_key == f"{rule_id}:192.168.1.1"
            assert a.group_name is not None
            assert "192.168.1.1" in a.group_name
            assert "Brute Force Alert" in a.group_name

    @pytest.mark.asyncio
    async def test_group_name_derivado_correctamente(self, session, rule_id):
        """group_name se deriva como '{rule_title} from {source_ip}'."""
        service = AlertService(session)

        datos = _alerta_base(rule_id)
        datos["group_key"] = f"{rule_id}:10.0.0.5"
        await service.crear_alerta(datos)

        updated = await service.agrupar_alertas_abiertas()
        assert updated == 1

        alertas, _ = await service.listar_alertas()
        assert len(alertas) == 1
        assert alertas[0].group_name == "Brute Force Alert from 10.0.0.5"

    @pytest.mark.asyncio
    async def test_risk_score_asignado_desde_entity_risks(self, session, rule_id):
        """risk_score se copia desde la tabla entity_risks."""
        service = AlertService(session)

        # Seedear entity_risks con un score conocido
        await _seed_entity_risk(session, "192.168.1.1", 0.75)

        datos = _alerta_base(rule_id)
        datos["group_key"] = f"{rule_id}:192.168.1.1"
        await service.crear_alerta(datos)

        updated = await service.agrupar_alertas_abiertas()
        assert updated == 1

        alertas, _ = await service.listar_alertas()
        assert len(alertas) == 1
        assert alertas[0].risk_score == 0.75

    @pytest.mark.asyncio
    async def test_alertas_sin_group_key_se_saltean(self, session, rule_id):
        """Alertas sin group_key no se modifican y no se cuentan."""
        service = AlertService(session)

        # Crear alerta SIN group_key
        datos = _alerta_base(rule_id)
        await service.crear_alerta(datos)

        updated = await service.agrupar_alertas_abiertas()
        assert updated == 0

        alertas, _ = await service.listar_alertas()
        assert len(alertas) == 1
        assert alertas[0].group_key is None
        assert alertas[0].group_name is None
        assert alertas[0].risk_score is None

    @pytest.mark.asyncio
    async def test_retorna_count_correcto(self, session, rule_id):
        """Retorna el conteo correcto de alertas actualizadas."""
        service = AlertService(session)

        # Grupo A: 2 alertas, Grupo B: 3 alertas
        for _ in range(2):
            datos = _alerta_base(rule_id)
            datos["group_key"] = f"{rule_id}:10.0.0.1"
            await service.crear_alerta(datos)

        for _ in range(3):
            datos = _alerta_base(rule_id)
            datos["group_key"] = f"{rule_id}:10.0.0.2"
            await service.crear_alerta(datos)

        updated = await service.agrupar_alertas_abiertas()
        assert updated == 5  # 2 + 3

    @pytest.mark.asyncio
    async def test_grupos_diferentes_se_procesan_separadamente(self, session, rule_id):
        """Alertas de diferentes group_keys se agrupan independientemente."""
        service = AlertService(session)

        await _seed_entity_risk(session, "10.0.0.1", 0.3)
        await _seed_entity_risk(session, "10.0.0.2", 0.9)

        for _ in range(2):
            datos = _alerta_base(rule_id)
            datos["group_key"] = f"{rule_id}:10.0.0.1"
            await service.crear_alerta(datos)

        datos = _alerta_base(rule_id)
        datos["group_key"] = f"{rule_id}:10.0.0.2"
        await service.crear_alerta(datos)

        updated = await service.agrupar_alertas_abiertas()
        assert updated == 3

        alertas, _ = await service.listar_alertas()

        # Verificar grupo 1
        grupo1 = [a for a in alertas if a.group_key == f"{rule_id}:10.0.0.1"]
        assert len(grupo1) == 2
        for a in grupo1:
            assert a.risk_score == 0.3
            assert "10.0.0.1" in a.group_name

        # Verificar grupo 2
        grupo2 = [a for a in alertas if a.group_key == f"{rule_id}:10.0.0.2"]
        assert len(grupo2) == 1
        assert grupo2[0].risk_score == 0.9
        assert "10.0.0.2" in grupo2[0].group_name

    @pytest.mark.asyncio
    async def test_entity_risk_inexistente_no_asigna_score(self, session, rule_id):
        """Si la entidad no tiene risk_score, se deja None."""
        service = AlertService(session)

        datos = _alerta_base(rule_id)
        datos["group_key"] = f"{rule_id}:192.168.99.99"
        await service.crear_alerta(datos)

        updated = await service.agrupar_alertas_abiertas()
        assert updated == 1

        alertas, _ = await service.listar_alertas()
        assert len(alertas) == 1
        # Sin entity_risk → risk_score queda None (no existe la entidad)
        assert alertas[0].risk_score is None
