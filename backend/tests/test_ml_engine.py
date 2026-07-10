"""Tests unitarios para el motor de ML (IsolationForest).

Prueba el comportamiento del MLEngine tanto con ML disponible
como sin dependencias (graceful fallback).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMLEngineAvailability:
    """ML disponible vs no disponible — graceful fallback."""

    def test_ml_available_flag_false_when_deps_missing(self):
        """ML_AVAILABLE es False cuando numpy/sklearn no se importan."""
        with patch("app.services.ml_engine.ML_AVAILABLE", False):
            from app.services.ml_engine import MLEngine

            engine = MLEngine(session_factory=MagicMock())
            assert engine.available is False

    @pytest.mark.asyncio
    async def test_score_returns_none_when_ml_unavailable(self):
        """score() retorna None cuando ML no está disponible."""
        with patch("app.services.ml_engine.ML_AVAILABLE", False):
            from app.services.ml_engine import MLEngine

            engine = MLEngine(session_factory=MagicMock())
            result = await engine.score({"source_port": 443})
            assert result is None

    @pytest.mark.asyncio
    async def test_init_async_noop_when_ml_unavailable(self):
        """init_async no hace nada cuando ML no está disponible."""
        with patch("app.services.ml_engine.ML_AVAILABLE", False):
            from app.services.ml_engine import MLEngine

            engine = MLEngine(session_factory=MagicMock())
            await engine.init_async()
            assert engine._trained is False
            assert engine.available is False


class TestFeatureExtraction:
    """Extracción de features numéricas de un evento_dict."""

    def test_extract_features_full(self):
        """Todas las features numéricas se extraen correctamente."""
        from app.services.ml_engine import MLEngine

        engine = MLEngine(session_factory=MagicMock())

        evento = {
            "source_port": 443,
            "destination_port": 80,
            "event_count": 5,
            "duration": 1.5,
            "bytes_sent": 1024,
            "bytes_received": 2048,
        }
        features = engine._extract_features(evento)
        assert features is not None
        assert len(features) == 6
        assert features[0] == 443.0  # source_port
        assert features[1] == 80.0  # destination_port
        assert features[2] == 5.0  # event_count
        assert features[3] == 1.5  # duration
        assert features[4] == 1024.0  # bytes_sent
        assert features[5] == 2048.0  # bytes_received

    def test_extract_features_no_numerics(self):
        """Sin campos numéricos → retorna None."""
        from app.services.ml_engine import MLEngine

        engine = MLEngine(session_factory=MagicMock())

        evento = {"event_type": "auth", "source": "syslog", "severity": "high"}
        features = engine._extract_features(evento)
        assert features is None

    def test_extract_features_mixed(self):
        """Mezcla de campos numéricos y no numéricos."""
        from app.services.ml_engine import MLEngine

        engine = MLEngine(session_factory=MagicMock())

        evento = {"source_port": 443, "event_type": "auth", "duration": None}
        features = engine._extract_features(evento)
        assert features is not None
        assert len(features) == 6
        assert features[0] == 443.0  # source_port
        assert features[3] == 0.0  # duration (None → 0.0)

    def test_extract_features_partial_numerics(self):
        """Solo algunos campos son numéricos, otros son strings."""
        from app.services.ml_engine import MLEngine

        engine = MLEngine(session_factory=MagicMock())

        evento = {
            "source_port": "invalid",
            "destination_port": 80,
            "bytes_sent": "N/A",
        }
        features = engine._extract_features(evento)
        assert features is not None
        assert features[0] == 0.0  # invalid converted to 0.0
        assert features[1] == 80.0
        assert features[4] == 0.0  # N/A converted to 0.0

    def test_feature_vector_length(self):
        """Feature vector length matches CAMPOS_NUMERICOS."""
        from app.services.ml_engine import MLEngine
        from app.services.analysis_service import CAMPOS_NUMERICOS

        engine = MLEngine(session_factory=MagicMock())

        evento = {
            "source_port": 443,
            "destination_port": 80,
            "event_count": 5,
            "duration": 1.5,
            "bytes_sent": 1024,
            "bytes_received": 2048,
        }
        features = engine._extract_features(evento)
        assert features is not None
        assert len(features) == len(CAMPOS_NUMERICOS)


class TestMLEngineScoring:
    """Scoring de anomalías con IsolationForest."""

    @pytest.mark.asyncio
    async def test_score_returns_none_when_model_not_trained(self):
        """score() retorna None si el modelo no está entrenado."""
        from app.services.ml_engine import MLEngine

        engine = MLEngine(session_factory=MagicMock())
        # Sin entrenar — model = None
        result = await engine.score({"source_port": 443})
        assert result is None

    @pytest.mark.asyncio
    async def test_score_returns_none_when_no_features(self):
        """score() retorna None si no hay features numéricas."""
        from app.services.ml_engine import MLEngine

        engine = MLEngine(session_factory=MagicMock())
        engine._trained = True
        # Para este test, necesitamos mockear ML_AVAILABLE y _model
        # ya que en realidad queremos probar el camino de _extract_features
        with patch("app.services.ml_engine.ML_AVAILABLE", True):
            # Mock model so _predict path isn't taken
            engine._model = MagicMock()
            result = await engine.score({"event_type": "auth"})
            assert result is None

    def test_predict_returns_float_when_model_ready(self):
        """_predict retorna un score float cuando el modelo existe."""
        import numpy as np
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler

        from app.services.ml_engine import MLEngine

        # Train a tiny model in-process for test
        engine = MLEngine(session_factory=MagicMock())
        engine._scaler = StandardScaler()
        X_train = np.array([[1.0, 2.0], [2.0, 3.0], [3.0, 4.0]])
        engine._scaler.fit(X_train)
        engine._model = IsolationForest(
            contamination=0.1, random_state=42, n_estimators=10
        )
        engine._model.fit(engine._scaler.transform(X_train))
        engine._trained = True

        score = engine._predict([1.5, 2.5])
        assert isinstance(score, float)
        # Score is in [-1, 1] range approximately
        assert -1.0 <= score <= 1.0
