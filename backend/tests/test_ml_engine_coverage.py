"""Additional coverage tests for ml_engine.py.

Covers: ML_AVAILABLE fallback (22-26), init_async failure (67-68),
score with exception (84-100), _extract_features not available (110),
_predict not available (134), _train_model not available (144),
_train_model full path (172-208), shutdown (212).

All tests use mocks for DB — no Docker required.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Mock helpers ─────────────────────────────────────────────────────────


def _make_session_factory(session):
    """Create a mock session factory for `async with factory() as session:`."""
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


def _make_broken_factory(error_msg="db fail"):
    """Create a session factory that raises on __aenter__."""
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError(error_msg))
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


def _make_mock_events(count):
    """Create mock NormalizedEvent objects with numeric attributes."""
    events = []
    for i in range(count):
        ev = MagicMock()
        ev.source_port = 8080 + (i % 100)
        ev.destination_port = 443
        ev.event_count = 1 + (i % 50)
        ev.duration = 0.1 + (i % 10) * 0.5
        ev.bytes_sent = 1024 + i * 10
        ev.bytes_received = 2048 + i * 10
        events.append(ev)
    return events


def _make_mock_events_with_nones(count):
    """Create mock events where some numeric fields are None."""
    events = []
    for i in range(count):
        ev = MagicMock()
        ev.source_port = 8080 + (i % 100) if i % 3 != 0 else None
        ev.destination_port = 443
        ev.event_count = None if i % 5 == 0 else 1 + (i % 50)
        ev.duration = 0.1 + (i % 10) * 0.5
        ev.bytes_sent = 1024 + i * 10
        ev.bytes_received = 2048 + i * 10
        events.append(ev)
    return events


def _make_train_session(events):
    """Create a mock session that returns events for training queries."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = events
    mock_session.execute.return_value = mock_result
    return _make_session_factory(mock_session)


# ══════════════════════════════════════════════════════════════════════════
# ML_AVAILABLE fallback paths
# ══════════════════════════════════════════════════════════════════════════


class TestMLAvailableFallback:
    """Behavior when numpy/sklearn are not installed."""

    def test_import_fallback_sets_flags(self):
        with patch("app.services.ml_engine.ML_AVAILABLE", False):
            from app.services.ml_engine import MLEngine

            engine = MLEngine(session_factory=MagicMock())
            assert engine.available is False

    def test_extract_features_returns_none_when_unavailable(self):
        with patch("app.services.ml_engine.ML_AVAILABLE", False):
            from app.services.ml_engine import MLEngine

            engine = MLEngine(session_factory=MagicMock())
            result = engine._extract_features({"source_port": 443})
            assert result is None

    def test_predict_returns_zero_when_unavailable(self):
        with patch("app.services.ml_engine.ML_AVAILABLE", False):
            from app.services.ml_engine import MLEngine

            engine = MLEngine(session_factory=MagicMock())
            result = engine._predict([1.0, 2.0])
            assert result == 0.0

    @pytest.mark.asyncio
    async def test_train_model_returns_when_unavailable(self):
        with patch("app.services.ml_engine.ML_AVAILABLE", False):
            from app.services.ml_engine import MLEngine

            engine = MLEngine(session_factory=MagicMock())
            await engine._train_model()
            assert engine._trained is False

    @pytest.mark.asyncio
    async def test_init_async_returns_when_unavailable(self):
        with patch("app.services.ml_engine.ML_AVAILABLE", False):
            from app.services.ml_engine import MLEngine

            engine = MLEngine(session_factory=MagicMock())
            await engine.init_async()
            assert engine._trained is False


# ══════════════════════════════════════════════════════════════════════════
# init_async — training failure (lines 67-68)
# ══════════════════════════════════════════════════════════════════════════


class TestInitAsyncFailure:
    """init_async handles training failures gracefully."""

    @pytest.mark.asyncio
    async def test_init_async_training_failure(self):
        from app.services.ml_engine import ML_AVAILABLE, MLEngine

        if not ML_AVAILABLE:
            pytest.skip("ML deps not installed")

        engine = MLEngine(session_factory=MagicMock())
        await engine.init_async()
        assert engine._trained is False


# ══════════════════════════════════════════════════════════════════════════
# score — exception handling (lines 84-100)
# ══════════════════════════════════════════════════════════════════════════


class TestScoreExceptions:
    """score() handles exceptions gracefully."""

    @pytest.mark.asyncio
    async def test_score_returns_none_on_exception(self):
        from app.services.ml_engine import ML_AVAILABLE, MLEngine

        if not ML_AVAILABLE:
            pytest.skip("ML deps not installed")

        engine = MLEngine(session_factory=MagicMock())
        engine._model = MagicMock()
        engine._trained = True

        with patch("app.services.ml_engine.ML_AVAILABLE", True):
            with patch.object(engine, "_extract_features", return_value=[1.0, 2.0]):
                with patch.object(
                    engine, "_predict", side_effect=RuntimeError("predict fail")
                ):
                    result = await engine.score({"source_port": 443})
                    assert result is None

    @pytest.mark.asyncio
    async def test_score_retrain_trigger(self):
        from app.services.ml_engine import ML_AVAILABLE, MLEngine

        if not ML_AVAILABLE:
            pytest.skip("ML deps not installed")

        engine = MLEngine(session_factory=MagicMock(), retrain_interval=3)
        engine._model = MagicMock()
        engine._trained = True

        with patch("app.services.ml_engine.ML_AVAILABLE", True):
            with patch.object(engine, "_extract_features", return_value=[1.0, 2.0]):
                with patch.object(engine, "_predict", return_value=0.5):
                    with patch.object(
                        engine, "_train_model", new_callable=AsyncMock
                    ) as mock_train:
                        for _ in range(3):
                            await engine.score({"source_port": 443})
                        mock_train.assert_called()

    @pytest.mark.asyncio
    async def test_score_no_retrain_below_interval(self):
        from app.services.ml_engine import ML_AVAILABLE, MLEngine

        if not ML_AVAILABLE:
            pytest.skip("ML deps not installed")

        engine = MLEngine(session_factory=MagicMock(), retrain_interval=10)
        engine._model = MagicMock()
        engine._trained = True

        with patch("app.services.ml_engine.ML_AVAILABLE", True):
            with patch.object(engine, "_extract_features", return_value=[1.0, 2.0]):
                with patch.object(engine, "_predict", return_value=0.5):
                    with patch.object(
                        engine, "_train_model", new_callable=AsyncMock
                    ) as mock_train:
                        await engine.score({"source_port": 443})
                        mock_train.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# _extract_features — edge cases
# ══════════════════════════════════════════════════════════════════════════


class TestExtractFeaturesEdgeCases:
    """Feature extraction edge cases."""

    def test_all_zero_features_returns_none(self):
        from app.services.ml_engine import MLEngine

        engine = MLEngine(session_factory=MagicMock())
        features = engine._extract_features({"source_port": 0, "destination_port": 0})
        assert features is None

    def test_non_numeric_string_fields(self):
        from app.services.ml_engine import MLEngine

        engine = MLEngine(session_factory=MagicMock())
        features = engine._extract_features({"source_port": "not-a-number"})
        assert features is None

    def test_partial_non_numeric(self):
        from app.services.ml_engine import MLEngine

        engine = MLEngine(session_factory=MagicMock())
        features = engine._extract_features({"source_port": 443, "duration": "invalid"})
        assert features is not None
        assert features[0] == 443.0
        assert features[3] == 0.0


# ══════════════════════════════════════════════════════════════════════════
# _train_model — full path (lines 172-208) using mock events
# ══════════════════════════════════════════════════════════════════════════


class TestTrainModelFull:
    """Full training path with mocked DB events."""

    @pytest.mark.asyncio
    async def test_train_model_enough_events(self):
        from app.services.ml_engine import ML_AVAILABLE, MLEngine

        if not ML_AVAILABLE:
            pytest.skip("ML deps not installed")

        mock_events = _make_mock_events(60)
        factory = _make_train_session(mock_events)

        engine = MLEngine(factory)
        await engine._train_model()

        assert engine._trained is True
        assert engine._model is not None
        assert engine._scaler is not None

    @pytest.mark.asyncio
    async def test_train_model_not_enough_events(self):
        from app.services.ml_engine import ML_AVAILABLE, MLEngine

        if not ML_AVAILABLE:
            pytest.skip("ML deps not installed")

        mock_events = _make_mock_events(5)
        factory = _make_train_session(mock_events)

        engine = MLEngine(factory)
        await engine._train_model()

        assert engine._trained is False

    @pytest.mark.asyncio
    async def test_train_model_handles_db_error(self):
        from app.services.ml_engine import ML_AVAILABLE, MLEngine

        if not ML_AVAILABLE:
            pytest.skip("ML deps not installed")

        factory = _make_broken_factory("db fail")
        engine = MLEngine(factory)
        await engine._train_model()
        assert engine._trained is False

    @pytest.mark.asyncio
    async def test_train_model_with_invalid_values(self):
        from app.services.ml_engine import ML_AVAILABLE, MLEngine

        if not ML_AVAILABLE:
            pytest.skip("ML deps not installed")

        mock_events = _make_mock_events_with_nones(60)
        factory = _make_train_session(mock_events)

        engine = MLEngine(factory)
        await engine._train_model()

        assert engine._trained is True

    @pytest.mark.asyncio
    async def test_train_model_builds_correct_feature_matrix(self):
        from app.services.ml_engine import ML_AVAILABLE, MLEngine

        if not ML_AVAILABLE:
            pytest.skip("ML deps not installed")

        mock_events = _make_mock_events(60)
        factory = _make_train_session(mock_events)

        engine = MLEngine(factory)
        await engine._train_model()

        import numpy as np

        test_features = [8080.0, 443.0, 1.0, 0.1, 1024.0, 2048.0]
        x = np.array([test_features])
        x_scaled = engine._scaler.transform(x)
        score = engine._model.decision_function(x_scaled)[0]
        assert isinstance(score, float)


# ══════════════════════════════════════════════════════════════════════════
# score — full path with trained model (lines 84-100)
# ══════════════════════════════════════════════════════════════════════════


class TestScoreWithTrainedModel:
    """score() with a trained model and mocked DB."""

    @pytest.mark.asyncio
    async def test_score_returns_float(self):
        from app.services.ml_engine import ML_AVAILABLE, MLEngine

        if not ML_AVAILABLE:
            pytest.skip("ML deps not installed")

        mock_events = _make_mock_events(60)
        factory = _make_train_session(mock_events)

        engine = MLEngine(factory)
        await engine._train_model()

        result = await engine.score(
            {"source_port": 9999, "destination_port": 443, "bytes_sent": 5000}
        )
        assert result is not None
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_score_no_features_returns_none(self):
        from app.services.ml_engine import ML_AVAILABLE, MLEngine

        if not ML_AVAILABLE:
            pytest.skip("ML deps not installed")

        mock_events = _make_mock_events(60)
        factory = _make_train_session(mock_events)

        engine = MLEngine(factory)
        await engine._train_model()

        result = await engine.score({"event_type": "auth", "source": "syslog"})
        assert result is None

    @pytest.mark.asyncio
    async def test_score_anomalous_event_has_lower_score(self):
        from app.services.ml_engine import ML_AVAILABLE, MLEngine

        if not ML_AVAILABLE:
            pytest.skip("ML deps not installed")

        mock_events = _make_mock_events(60)
        factory = _make_train_session(mock_events)

        engine = MLEngine(factory)
        await engine._train_model()

        normal_score = await engine.score(
            {"source_port": 8085, "destination_port": 443, "bytes_sent": 1500}
        )
        anomalous_score = await engine.score(
            {"source_port": 1, "destination_port": 1, "bytes_sent": 1}
        )

        assert normal_score is not None
        assert anomalous_score is not None
        assert anomalous_score < normal_score


# ══════════════════════════════════════════════════════════════════════════
# shutdown (line 212)
# ══════════════════════════════════════════════════════════════════════════


class TestShutdown:
    """shutdown method."""

    @pytest.mark.asyncio
    async def test_shutdown_closes_executor(self):
        from app.services.ml_engine import MLEngine

        engine = MLEngine(session_factory=MagicMock())
        await engine.shutdown()
        # Executor should be shut down — verify by checking the flag
        assert engine._executor._shutdown is True
