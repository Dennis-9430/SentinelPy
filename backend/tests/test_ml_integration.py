"""Tests de integración para ML scoring en el pipeline de análisis.

Verifica que el MLEngine se integra correctamente con AnalysisService
y que los scores fluyen a analysis_data.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestMLIntegration:
    """ML scoring integration with AnalysisService."""

    @pytest.mark.asyncio
    async def test_analyze_includes_ml_score_when_available(self):
        """analysis_data incluye ml_score cuando ML está disponible."""
        from app.services.analysis_service import AnalysisService

        # Create service with mocked MLEngine
        svc = AnalysisService(session_factory=MagicMock())

        # Inject a mock ML engine that returns a known score
        mock_ml = MagicMock()
        mock_ml.available = True
        mock_ml.score = AsyncMock(return_value=-0.5)
        svc._ml_engine = mock_ml

        # Mock the persist method to capture what would be saved
        svc._persist_analysis_data = AsyncMock()  # type: ignore[method-assign]
        # Mock zscores to return something
        svc._compute_event_zscores = MagicMock(return_value={"source_port": 3.5})  # type: ignore[method-assign]
        svc._update_entity_risk = AsyncMock()  # type: ignore[method-assign]

        await svc.analyze(
            evento_id="test-uuid",
            evento_dict={"source_port": 9999, "severity": "high"},
        )

        # Verify ml_engine.score was called
        mock_ml.score.assert_awaited_once()

        # Verify _persist_analysis_data was called with analysis_data including ml_score
        svc._persist_analysis_data.assert_awaited_once_with(
            "test-uuid",
            {"zscores": {"source_port": 3.5}, "ml_score": -0.5},
        )

    @pytest.mark.asyncio
    async def test_analyze_skips_ml_when_not_available(self):
        """analysis_data NO incluye ml_score cuando ML no está disponible."""
        from app.services.analysis_service import AnalysisService

        svc = AnalysisService(session_factory=MagicMock())

        # ml_engine is None (not initialized)
        svc._ml_engine = None
        svc._persist_analysis_data = AsyncMock()  # type: ignore[method-assign]
        svc._compute_event_zscores = MagicMock(return_value={"source_port": 3.5})  # type: ignore[method-assign]
        svc._update_entity_risk = AsyncMock()  # type: ignore[method-assign]

        await svc.analyze(
            evento_id="test-uuid",
            evento_dict={"source_port": 9999, "severity": "high"},
        )

        # Verify _persist_analysis_data was called with zscores only
        svc._persist_analysis_data.assert_awaited_once_with(
            "test-uuid",
            {"zscores": {"source_port": 3.5}},
        )

    @pytest.mark.asyncio
    async def test_analyze_only_ml_score_when_no_zscores(self):
        """analysis_data incluye solo ml_score si no hay zscores."""
        from app.services.analysis_service import AnalysisService

        svc = AnalysisService(session_factory=MagicMock())

        # Mock ML engine to return a score
        mock_ml = MagicMock()
        mock_ml.available = True
        mock_ml.score = AsyncMock(return_value=-0.3)
        svc._ml_engine = mock_ml

        # No zscores (empty dict is falsy)
        svc._compute_event_zscores = MagicMock(return_value={})  # type: ignore[method-assign]
        svc._persist_analysis_data = AsyncMock()  # type: ignore[method-assign]
        svc._update_entity_risk = AsyncMock()  # type: ignore[method-assign]

        await svc.analyze(
            evento_id="test-uuid",
            evento_dict={"source_port": 50, "severity": "info"},
        )

        svc._persist_analysis_data.assert_awaited_once_with(
            "test-uuid",
            {"ml_score": -0.3},
        )

    @pytest.mark.asyncio
    async def test_analyze_neither_zscores_nor_ml(self):
        """analysis_data NO se persiste si no hay zscores ni ml_score."""
        from app.services.analysis_service import AnalysisService

        svc = AnalysisService(session_factory=MagicMock())

        # ml_engine is None, no zscores
        svc._ml_engine = None
        svc._persist_analysis_data = AsyncMock()  # type: ignore[method-assign]
        svc._compute_event_zscores = MagicMock(return_value={})  # type: ignore[method-assign]
        svc._update_entity_risk = AsyncMock()  # type: ignore[method-assign]

        await svc.analyze(
            evento_id="test-uuid",
            evento_dict={"source_port": 50, "severity": "info"},
        )

        # No analysis data to persist
        svc._persist_analysis_data.assert_not_awaited()
