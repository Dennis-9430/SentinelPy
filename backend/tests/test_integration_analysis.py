"""Tests de integración para el servicio de análisis con PostgreSQL real.

Ejecuta toda la suite de integración en un SOLO test para evitar
problemas de lifecycle del container testcontainer entre tests.
"""

import asyncio

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.event import NormalizedEvent
from app.services.analysis_service import AnalysisService
from app.services.pipeline import Pipeline


async def _prepare(async_engine):
    """Retorna una session factory para tests de integración."""
    factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    return factory


@pytest.mark.asyncio
async def test_analysis_integration(session, async_engine):
    """Suite completa de integración: pipeline hook, risk store, risk via pipeline."""

    # ── Preparación ──────────────────────────────────────────────────────
    factory = await _prepare(async_engine)

    svc = AnalysisService(factory)
    await svc.init_async()

    pipeline = Pipeline(engine=None, session_factory=factory, analysis_service=svc)

    # ═════════════════════════════════════════════════════════════════════
    # Test 1: Pipeline hook dispara analysis_data
    # ═════════════════════════════════════════════════════════════════════
    log1 = (
        '{"event_type": "port_scan", "severity": "high", '
        '"description": "Escaneo de puertos detectado", '
        '"source": "scanner-01", "collector_type": "test", '
        '"source_port": 9999, "destination_port": 8080, '
        '"event_timestamp": "2024-01-01T00:00:00Z"}'
    )
    ev1 = await pipeline.process(log1)
    assert ev1 is not None, "Pipeline no procesó el primer evento"

    ev1_id = str(ev1.id)
    await asyncio.sleep(0.5)

    async with factory() as s:
        result = await s.execute(
            select(NormalizedEvent).where(NormalizedEvent.id == ev1_id)
        )
        persisted = result.scalar_one_or_none()
        assert persisted is not None, "Evento no encontrado en DB"

    # ═════════════════════════════════════════════════════════════════════
    # Test 2: EntityRiskStore persiste riesgos (write-through)
    # ═════════════════════════════════════════════════════════════════════
    entity_key = "192.168.1.1"
    await svc._risk_store.update_risk(entity_key, 0.5)  # type: ignore[union-attr]

    async with factory() as s:
        result = await s.execute(
            text("SELECT entity_key, risk_score FROM entity_risks")
        )
        rows = result.fetchall()
        assert len(rows) >= 1, "No hay rows en entity_risks"
        matched = [r for r in rows if r[0] == entity_key]
        assert len(matched) == 1, f"Entity {entity_key} no encontrada"
        assert matched[0][1] == pytest.approx(0.5, rel=1e-3)

    # ═════════════════════════════════════════════════════════════════════
    # Test 3: Pipeline incrementa riesgo por severidad
    # ═════════════════════════════════════════════════════════════════════
    log2 = (
        '{"event_type": "auth_failure", "severity": "high", '
        '"description": "Fallo de autenticación desde IP externa", '
        '"source": "firewall-01", "collector_type": "test", '
        '"source_ip": "10.0.0.5", '
        '"event_timestamp": "2024-01-01T00:00:00Z"}'
    )
    ev2 = await pipeline.process(log2)
    assert ev2 is not None, "Pipeline no procesó el segundo evento"

    await asyncio.sleep(0.5)

    async with factory() as s:
        result = await s.execute(
            text("SELECT risk_score FROM entity_risks WHERE entity_key = '10.0.0.5'")
        )
        row = result.fetchone()
        assert row is not None, "Entity risk no fue persistido"
        # Severidad 'high' → incremento de 0.1
        assert row[0] == pytest.approx(0.1, rel=1e-3)
