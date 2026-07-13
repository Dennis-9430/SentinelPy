"""Tests unitarios para el servicio de análisis.

Prueba las funciones puras de z-score, baseline, y riesgo.
NO requiere base de datos — solo Python stdlib.
"""

import math

import pytest

from app.services.analysis_service import (
    _compute_zscore,
    _decay_risk,
    _increment_risk,
    _is_numeric,
)

# ══════════════════════════════════════════════════════════════════════════
# Tests: _is_numeric
# ══════════════════════════════════════════════════════════════════════════


class TestIsNumeric:
    """Verifica si un valor puede usarse para cálculo de z-score."""

    def test_int_es_numerico(self):
        assert _is_numeric(42) is True

    def test_float_es_numerico(self):
        assert _is_numeric(3.14) is True

    def test_string_no_es_numerico(self):
        assert _is_numeric("texto") is False

    def test_none_no_es_numerico(self):
        assert _is_numeric(None) is False

    def test_string_numerico_se_considera_no_numerico(self):
        """Por diseño, no convertimos strings — queremos valores nativos."""
        assert _is_numeric("42") is False


# ══════════════════════════════════════════════════════════════════════════
# Tests: _compute_zscore
# ══════════════════════════════════════════════════════════════════════════


class TestComputeZscore:
    """Cálculo de z-score: (value - mean) / std."""

    def test_zscore_positivo(self):
        """Valor muy por encima de la media da z-score positivo alto."""
        resultado = _compute_zscore(100, 50, 10)
        assert resultado is not None
        assert resultado == pytest.approx(5.0)

    def test_zscore_negativo(self):
        """Valor por debajo de la media da z-score negativo."""
        resultado = _compute_zscore(30, 50, 10)
        assert resultado is not None
        assert resultado == pytest.approx(-2.0)

    def test_zscore_cero_en_media(self):
        """Valor igual a la media da z-score 0."""
        resultado = _compute_zscore(50, 50, 10)
        assert resultado is not None
        assert resultado == pytest.approx(0.0)

    def test_zscore_none_si_std_cero(self):
        """Desvío estándar 0 → z-score None (no hay variación)."""
        resultado = _compute_zscore(50, 50, 0)
        assert resultado is None

    def test_zscore_none_si_std_negativo(self):
        """Desvío estándar negativo (inválido) → None."""
        resultado = _compute_zscore(50, 50, -1)
        assert resultado is None

    def test_zscore_con_floats(self):
        """Precisión con valores float."""
        resultado = _compute_zscore(10.5, 5.25, 2.5)
        assert resultado is not None
        assert resultado == pytest.approx(2.1)


# ══════════════════════════════════════════════════════════════════════════
# Tests: _increment_risk
# ══════════════════════════════════════════════════════════════════════════


class TestIncrementRisk:
    """Incremento de riesgo con cap en máximo configurable."""

    def test_incremento_normal(self):
        """0.2 + 0.1 = 0.3."""
        resultado = _increment_risk(0.2, 0.1, 1.0)
        assert resultado == pytest.approx(0.3)

    def test_cap_en_maximo(self):
        """0.95 + 0.1 se capa en 1.0."""
        resultado = _increment_risk(0.95, 0.1, 1.0)
        assert resultado == pytest.approx(1.0)

    def test_sin_incremento(self):
        """Sin incremento, el score no cambia."""
        resultado = _increment_risk(0.5, 0.0, 1.0)
        assert resultado == pytest.approx(0.5)

    def test_desde_cero(self):
        """Desde 0 con incremento positivo."""
        resultado = _increment_risk(0.0, 0.3, 1.0)
        assert resultado == pytest.approx(0.3)

    def test_max_risk_personalizado(self):
        """Cap personalizado diferente de 1.0."""
        resultado = _increment_risk(0.8, 0.3, 0.9)
        assert resultado == pytest.approx(0.9)


# ══════════════════════════════════════════════════════════════════════════
# Tests: _decay_risk
# ══════════════════════════════════════════════════════════════════════════


class TestDecayRisk:
    """Decaimiento exponencial del riesgo."""

    def test_decaimiento_parcial(self):
        """Score 0.8 decae después de 1 hora con decay_rate 0.5."""
        # decay_rate 0.5 significa que el score se reduce a la mitad en 1 hora
        resultado = _decay_risk(0.8, 0.5, 3600)
        # score * exp(-rate * time/3600) = 0.8 * exp(-0.5 * 1) = 0.8 * exp(-0.5)
        esperado = 0.8 * math.exp(-0.5)
        assert resultado == pytest.approx(esperado, rel=1e-6)

    def test_score_cero_sigue_cero(self):
        """Score 0.0 después de decay sigue siendo 0.0."""
        resultado = _decay_risk(0.0, 0.5, 3600)
        assert resultado == pytest.approx(0.0)

    def test_sin_tiempo_transcurrido(self):
        """Sin tiempo transcurrido, el score no cambia."""
        resultado = _decay_risk(0.5, 0.5, 0)
        assert resultado == pytest.approx(0.5)

    def test_decaimiento_completo(self):
        """Después de mucho tiempo, el score tiende a 0."""
        resultado = _decay_risk(0.5, 0.5, 86400 * 30)  # 30 días
        assert resultado < 0.01

    def test_decay_rate_cero(self):
        """Con decay_rate 0, el score no decae nunca."""
        resultado = _decay_risk(0.8, 0.0, 3600)
        assert resultado == pytest.approx(0.8)


# ══════════════════════════════════════════════════════════════════════════
# Tests: Funciones de baseline (estadísticas)
# ══════════════════════════════════════════════════════════════════════════


class TestBaselineStats:
    """Cálculo de media y desvío estándar para baselines."""

    def test_mean_y_std_de_valores_simples(self):
        from app.services.analysis_service import _compute_baseline_stats

        valores = [10.0, 20.0, 30.0, 40.0, 50.0]
        mean, std = _compute_baseline_stats(valores)
        assert mean == pytest.approx(30.0)
        assert std == pytest.approx(
            15.811388, rel=1e-4
        )  # population std with ddof=1

    def test_valor_unico(self):
        """Un solo valor → mean es el valor, std es 0."""
        from app.services.analysis_service import _compute_baseline_stats

        mean, std = _compute_baseline_stats([42.0])
        assert mean == pytest.approx(42.0)
        assert std == pytest.approx(0.0)

    def test_lista_vacia(self):
        """Lista vacía → ambos son 0."""
        from app.services.analysis_service import _compute_baseline_stats

        mean, std = _compute_baseline_stats([])
        assert mean == 0.0
        assert std == 0.0

    def test_valores_constantes(self):
        """Todos iguales → mean es el valor, std es 0."""
        from app.services.analysis_service import _compute_baseline_stats

        mean, std = _compute_baseline_stats([5.0, 5.0, 5.0])
        assert mean == pytest.approx(5.0)
        assert std == pytest.approx(0.0)


# ══════════════════════════════════════════════════════════════════════════
# Tests: Extracción de campos numéricos de un evento
# ══════════════════════════════════════════════════════════════════════════


class TestExtractNumericFields:
    """Extrae campos numéricos relevantes de un evento para análisis."""

    def test_extrae_campos_numericos(self):
        from app.services.analysis_service import _extract_numeric_fields

        evento = {
            "source_port": 8080,
            "destination_port": 443,
            "severity": "high",
            "event_type": "auth_failure",
        }
        result = _extract_numeric_fields(evento)
        assert result == {"source_port": 8080, "destination_port": 443}

    def test_campos_none_se_excluyen(self):
        from app.services.analysis_service import _extract_numeric_fields

        evento = {"source_port": None, "destination_port": 443}
        result = _extract_numeric_fields(evento)
        assert result == {"destination_port": 443}

    def test_sin_campos_numericos(self):
        from app.services.analysis_service import _extract_numeric_fields

        evento = {"event_type": "auth_failure", "severity": "high"}
        result = _extract_numeric_fields(evento)
        assert result == {}
