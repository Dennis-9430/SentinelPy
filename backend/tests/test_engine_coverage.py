"""Additional coverage tests for engine.py.

Covers: _evaluar_regla with list conditions (219-223), NOT operator
in _evaluar_grupo (246-251), nested field with dot notation (284-291),
gte/lte operators (304, 308), not_exists/startswith/endswith (315-323),
unknown operator (339), in_list with None (354), regex with None (363),
startswith/endswith None checks (368-376), callback errors (413-414,
427-428).
"""

import pytest

from app.services.engine import CorrelationEngine


@pytest.fixture
def engine():
    return CorrelationEngine()


# ══════════════════════════════════════════════════════════════════════════
# _evaluar_regla — list conditions (lines 219-223)
# ══════════════════════════════════════════════════════════════════════════


class TestEvaluarReglaListConditions:
    """Covers the list-based conditions path in _evaluar_regla."""

    def test_list_conditions_all_match(self, engine):
        """A list of conditions (implicit AND) — all match."""
        regla = {
            "conditions": [
                {"field": "severity", "operator": "eq", "value": "high"},
                {"field": "event_type", "operator": "eq", "value": "auth"},
            ]
        }
        assert engine._evaluar_regla(regla, {"severity": "high", "event_type": "auth"})

    def test_list_conditions_one_fails(self, engine):
        """A list of conditions — one fails → whole list fails."""
        regla = {
            "conditions": [
                {"field": "severity", "operator": "eq", "value": "high"},
                {"field": "event_type", "operator": "eq", "value": "auth"},
            ]
        }
        assert not engine._evaluar_regla(
            regla, {"severity": "high", "event_type": "network"}
        )

    def test_dict_condition_simple(self, engine):
        """A dict condition (not group) — evaluates directly."""
        regla = {"conditions": {"field": "severity", "operator": "eq", "value": "high"}}
        assert engine._evaluar_regla(regla, {"severity": "high"})
        assert not engine._evaluar_regla(regla, {"severity": "low"})


# ══════════════════════════════════════════════════════════════════════════
# _evaluar_grupo — NOT operator (lines 246-251)
# ══════════════════════════════════════════════════════════════════════════


class TestEvaluarGrupoNot:
    """Covers the NOT branch in _evaluar_grupo."""

    def test_not_operator_with_condition(self, engine):
        """NOT operator negates a single condition."""
        grupo = {
            "operator": "NOT",
            "conditions": [
                {"field": "severity", "operator": "eq", "value": "critical"}
            ],
        }
        # severity is NOT critical → True
        assert engine._evaluar_grupo(grupo, {"severity": "high"})
        # severity IS critical → False
        assert not engine._evaluar_grupo(grupo, {"severity": "critical"})

    def test_not_operator_empty_conditions(self, engine):
        """NOT with empty conditions returns True."""
        grupo = {"operator": "NOT", "conditions": []}
        assert engine._evaluar_grupo(grupo, {"severity": "high"})

    def test_unknown_operator_returns_false(self, engine):
        """Unknown operator in group returns False."""
        grupo = {
            "operator": "XOR",
            "conditions": [{"field": "a", "operator": "eq", "value": "b"}],
        }
        assert not engine._evaluar_grupo(grupo, {"a": "b"})


# ══════════════════════════════════════════════════════════════════════════
# _evaluar_condicion — nested dot-notation fields (lines 284-291)
# ══════════════════════════════════════════════════════════════════════════


class TestEvaluarCondicionNestedFields:
    """Covers dot-notation nested field access."""

    def test_nested_field_match(self, engine):
        """Dot-notation resolves nested dict fields."""
        evento = {"network": {"src_ip": "10.0.0.1"}}
        condicion = {"field": "network.src_ip", "operator": "eq", "value": "10.0.0.1"}
        assert engine._evaluar_condicion(condicion, evento)

    def test_nested_field_missing_intermediate(self, engine):
        """Missing intermediate dict returns None → condition fails."""
        evento = {"source_ip": "10.0.0.1"}
        condicion = {"field": "network.src_ip", "operator": "eq", "value": "10.0.0.1"}
        assert not engine._evaluar_condicion(condicion, evento)

    def test_nested_field_non_dict_intermediate(self, engine):
        """Non-dict intermediate value returns None."""
        evento = {"network": "not-a-dict"}
        condicion = {"field": "network.src_ip", "operator": "eq", "value": "10.0.0.1"}
        assert not engine._evaluar_condicion(condicion, evento)

    def test_no_field_condition(self, engine):
        """Condition with no field → valor_evento is None."""
        condicion = {"operator": "eq", "value": "test"}
        assert not engine._evaluar_condicion(condicion, {"anything": "test"})


# ══════════════════════════════════════════════════════════════════════════
# _evaluar_condicion — gte/lte operators (lines 304, 308)
# ══════════════════════════════════════════════════════════════════════════


class TestEvaluarCondicionGteLte:
    """Covers gte and lte operators."""

    def test_gte_equal(self, engine):
        condicion = {"field": "port", "operator": "gte", "value": 80}
        assert engine._evaluar_condicion(condicion, {"port": 80})

    def test_gte_greater(self, engine):
        condicion = {"field": "port", "operator": "gte", "value": 80}
        assert engine._evaluar_condicion(condicion, {"port": 81})

    def test_gte_less_fails(self, engine):
        condicion = {"field": "port", "operator": "gte", "value": 80}
        assert not engine._evaluar_condicion(condicion, {"port": 79})

    def test_lte_equal(self, engine):
        condicion = {"field": "port", "operator": "lte", "value": 80}
        assert engine._evaluar_condicion(condicion, {"port": 80})

    def test_lte_less(self, engine):
        condicion = {"field": "port", "operator": "lte", "value": 80}
        assert engine._evaluar_condicion(condicion, {"port": 79})

    def test_lte_greater_fails(self, engine):
        condicion = {"field": "port", "operator": "lte", "value": 80}
        assert not engine._evaluar_condicion(condicion, {"port": 81})


# ══════════════════════════════════════════════════════════════════════════
# _evaluar_condicion — not_exists, startswith, endswith (lines 315-323)
# ══════════════════════════════════════════════════════════════════════════


class TestEvaluarCondicionNotExistStartswithEndswith:
    """Covers not_exists, startswith, and endswith operators."""

    def test_not_exists_field_missing(self, engine):
        condicion = {"field": "missing", "operator": "not_exists"}
        assert engine._evaluar_condicion(condicion, {"other": "val"})

    def test_not_exists_field_present(self, engine):
        condicion = {"field": "name", "operator": "not_exists"}
        assert not engine._evaluar_condicion(condicion, {"name": "test"})

    def test_startswith_match(self, engine):
        condicion = {"field": "name", "operator": "startswith", "value": "admin"}
        assert engine._evaluar_condicion(condicion, {"name": "Administrator"})

    def test_startswith_no_match(self, engine):
        condicion = {"field": "name", "operator": "startswith", "value": "root"}
        assert not engine._evaluar_condicion(condicion, {"name": "admin"})

    def test_startswith_none_value(self, engine):
        condicion = {"field": "name", "operator": "startswith", "value": "test"}
        assert not engine._evaluar_condicion(condicion, {"name": None})

    def test_startswith_none_evento_value(self, engine):
        condicion = {"field": "name", "operator": "startswith", "value": None}
        assert not engine._evaluar_condicion(condicion, {"name": "test"})

    def test_endswith_match(self, engine):
        condicion = {"field": "path", "operator": "endswith", "value": ".log"}
        assert engine._evaluar_condicion(condicion, {"path": "/var/log/syslog.log"})

    def test_endswith_no_match(self, engine):
        condicion = {"field": "path", "operator": "endswith", "value": ".log"}
        assert not engine._evaluar_condicion(condicion, {"path": "/var/log/syslog.txt"})

    def test_endswith_none_value(self, engine):
        condicion = {"field": "path", "operator": "endswith", "value": ".log"}
        assert not engine._evaluar_condicion(condicion, {"path": None})

    def test_endswith_none_evento_value(self, engine):
        condicion = {"field": "path", "operator": "endswith", "value": None}
        assert not engine._evaluar_condicion(condicion, {"path": "test.log"})

    def test_unknown_operator_returns_false(self, engine):
        """Unknown operator returns False."""
        condicion = {"field": "x", "operator": "UNKNOWN", "value": "y"}
        assert not engine._evaluar_condicion(condicion, {"x": "y"})


# ══════════════════════════════════════════════════════════════════════════
# _evaluar_condicion — null checks for _in_list, _regex (lines 354, 363)
# ══════════════════════════════════════════════════════════════════════════


class TestNullChecks:
    """Null value handling for operators."""

    def test_in_list_none_value(self, engine):
        """in operator with None event value returns False."""
        condicion = {"field": "x", "operator": "in", "value": ["a", "b"]}
        assert not engine._evaluar_condicion(condicion, {"x": None})

    def test_regex_none_event_value(self, engine):
        """regex with None event value returns False."""
        condicion = {"field": "x", "operator": "regex", "value": ".*"}
        assert not engine._evaluar_condicion(condicion, {"x": None})

    def test_regex_none_pattern(self, engine):
        """regex with None pattern returns False."""
        condicion = {"field": "x", "operator": "regex", "value": None}
        assert not engine._evaluar_condicion(condicion, {"x": "test"})

    def test_contains_none_event_value(self, engine):
        """contains with None event value returns False."""
        condicion = {"field": "x", "operator": "contains", "value": "test"}
        assert not engine._evaluar_condicion(condicion, {"x": None})

    def test_contains_none_value(self, engine):
        """contains with None comparison value returns False."""
        condicion = {"field": "x", "operator": "contains", "value": None}
        assert not engine._evaluar_condicion(condicion, {"x": "test"})


# ══════════════════════════════════════════════════════════════════════════
# Callback error handling (lines 413-414, 427-428)
# ══════════════════════════════════════════════════════════════════════════


class TestCallbackErrors:
    """Callback exceptions are caught and logged, not propagated."""

    @pytest.mark.asyncio
    async def test_create_callback_error_does_not_propagate(self, engine):
        """Error in create callback doesn't prevent alert creation."""

        async def bad_callback(alerta):
            raise RuntimeError("callback boom")

        regla = {
            "id": "rule-cb-err",
            "title": "CB error test",
            "conditions": {"field": "severity", "operator": "eq", "value": "high"},
            "alert_title": "CB error alert",
            "alert_severity": "high",
            "status": "active",
        }

        engine.registrar_callback(bad_callback)
        engine.cargar_reglas([regla])

        # Should not raise despite callback error
        alertas = await engine.evaluate({"severity": "high"})
        assert len(alertas) == 1

    @pytest.mark.asyncio
    async def test_update_callback_error_does_not_propagate(self, engine):
        """Error in update callback doesn't crash the engine."""

        async def bad_update(datos):
            raise RuntimeError("update boom")

        regla = {
            "id": "rule-upd-err",
            "title": "Update error test",
            "conditions": {"field": "severity", "operator": "eq", "value": "high"},
            "alert_title": "Update error alert",
            "alert_severity": "high",
            "correlation_window": 300,
            "status": "active",
        }

        engine.registrar_callback_actualizar(bad_update)
        engine.cargar_reglas([regla])

        # First match creates alert
        await engine.evaluate({"severity": "high"})
        # Second match triggers update callback — should not raise
        alertas = await engine.evaluate({"severity": "high"})
        assert len(alertas) == 0  # Update only, no new alert
