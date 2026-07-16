"""Tests for engine IOC injection — verifies engine handles TI data correctly.

The engine's _evaluar_condicion already supports nested dot notation.
These tests verify it works with ti.matches data when present, and
doesn't crash when absent.
"""

import pytest
from unittest.mock import MagicMock

from app.services.engine import CorrelationEngine


@pytest.fixture
def engine():
    return CorrelationEngine()


class TestEngineTIInjection:
    """Verify engine works with TI data in event_dict."""

    def test_engine_handles_missing_ti_data(self, engine):
        """Engine evaluates conditions normally when ti data is absent."""
        condicion = {"field": "severity", "operator": "eq", "value": "high"}
        evento = {"severity": "high", "source_ip": "1.2.3.4"}
        assert engine._evaluar_condicion(condicion, evento) is True

    def test_engine_handles_empty_ti_dict(self, engine):
        """Engine doesn't crash when ti is empty dict."""
        condicion = {"field": "severity", "operator": "eq", "value": "high"}
        evento = {"severity": "high", "ti": {}}
        assert engine._evaluar_condicion(condicion, evento) is True

    def test_engine_handles_ti_matches_absent(self, engine):
        """Engine handles ti dict without matches key."""
        condicion = {"field": "severity", "operator": "eq", "value": "high"}
        evento = {"severity": "high", "ti": {"other": "data"}}
        assert engine._evaluar_condicion(condicion, evento) is True

    def test_engine_reads_ti_nested_field(self, engine):
        """Engine can read nested ti field via dot notation."""
        condicion = {"field": "ti.source", "operator": "eq", "value": "abuseipdb"}
        evento = {"ti": {"source": "abuseipdb"}}
        assert engine._evaluar_condicion(condicion, evento) is True

    def test_engine_ti_confidence_gt(self, engine):
        """Engine evaluates gt on nested ti field."""
        condicion = {"field": "ti.confidence", "operator": "gt", "value": 80}
        evento = {"ti": {"confidence": 95}}
        assert engine._evaluar_condicion(condicion, evento) is True

    def test_engine_ti_confidence_lt(self, engine):
        """Engine evaluates lt on nested ti field."""
        condicion = {"field": "ti.confidence", "operator": "lt", "value": 50}
        evento = {"ti": {"confidence": 30}}
        assert engine._evaluar_condicion(condicion, evento) is True

    def test_engine_ti_confidence_not_matching(self, engine):
        """Engine returns False when ti condition doesn't match."""
        condicion = {"field": "ti.confidence", "operator": "gt", "value": 80}
        evento = {"ti": {"confidence": 50}}
        assert engine._evaluar_condicion(condicion, evento) is False

    def test_engine_ti_missing_nested_field(self, engine):
        """Engine returns None/falsy when nested ti field doesn't exist."""
        condicion = {"field": "ti.nonexistent", "operator": "eq", "value": "x"}
        evento = {"ti": {"confidence": 95}}
        assert engine._evaluar_condicion(condicion, evento) is False

    def test_engine_combined_ti_and_regular_fields(self, engine):
        """Engine evaluates conditions mixing TI and regular fields."""
        condicion_severity = {"field": "severity", "operator": "eq", "value": "high"}
        condicion_ti = {"field": "ti.confidence", "operator": "gte", "value": 80}
        evento = {"severity": "high", "ti": {"confidence": 90}}
        assert engine._evaluar_condicion(condicion_severity, evento) is True
        assert engine._evaluar_condicion(condicion_ti, evento) is True
