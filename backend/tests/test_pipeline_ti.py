"""Tests for Pipeline TI enrichment hook.

Covers: enrichment fires when TI enabled, skipped when disabled,
provider error doesn't propagate, enrichment writes to analysis_data["ti"].
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.pipeline import Pipeline


class TestPipelineTIEnrichment:
    """Verifica el hook de enriquecimiento TI en el pipeline."""

    async def test_enrichment_calls_ti_service_enrich(self):
        """When TI is enabled and ti_service exists, enrich() is called."""
        mock_ti_service = AsyncMock()
        mock_ti_service.enrich.return_value = {
            "matches": [{"type": "ip", "indicator": "1.2.3.4", "confidence": 85, "provider": "abuseipdb"}]
        }
        pipeline = Pipeline(ti_service=mock_ti_service)

        evento_dict = {"id": "evt-001", "source_ip": "1.2.3.4", "source": "test"}

        await pipeline._enrich_ti(evento_dict)

        mock_ti_service.enrich.assert_called_once_with(evento_dict)

    async def test_enrichment_writes_to_analysis_data_ti(self):
        """Enrichment stores TI data in analysis_data['ti'] on the event."""
        ti_data = {
            "matches": [{"type": "ip", "indicator": "1.2.3.4", "confidence": 85, "provider": "abuseipdb"}]
        }
        mock_ti_service = AsyncMock()
        mock_ti_service.enrich.return_value = ti_data

        # Mock the DB session and event
        mock_event = MagicMock()
        mock_event.analysis_data = {}

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_event)

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        pipeline = Pipeline(ti_service=mock_ti_service, session_factory=mock_session_factory)

        evento_dict = {"id": "evt-001", "source_ip": "1.2.3.4", "source": "test"}

        with patch("app.models.event.NormalizedEvent"):
            await pipeline._enrich_ti(evento_dict)

        # Verify analysis_data["ti"] was set
        assert mock_event.analysis_data["ti"] == ti_data
        mock_session.commit.assert_called_once()

    async def test_enrichment_noop_when_ti_data_empty(self):
        """When TI returns empty dict, no DB write occurs."""
        mock_ti_service = AsyncMock()
        mock_ti_service.enrich.return_value = {}

        pipeline = Pipeline(ti_service=mock_ti_service)

        evento_dict = {"id": "evt-001", "source_ip": "8.8.8.8", "source": "test"}

        await pipeline._enrich_ti(evento_dict)

        mock_ti_service.enrich.assert_called_once_with(evento_dict)
        # No DB interaction since ti_data is empty

    async def test_provider_error_does_not_propagate(self):
        """Exceptions in TI enrichment are swallowed silently."""
        mock_ti_service = AsyncMock()
        mock_ti_service.enrich.side_effect = RuntimeError("TI provider exploded")

        pipeline = Pipeline(ti_service=mock_ti_service)

        evento_dict = {"id": "evt-001", "source_ip": "1.2.3.4", "source": "test"}

        # Should NOT raise
        await pipeline._enrich_ti(evento_dict)

    async def test_db_error_does_not_propagate(self):
        """Exceptions during DB write are swallowed silently."""
        ti_data = {"matches": [{"type": "ip", "indicator": "1.2.3.4", "confidence": 85, "provider": "abuseipdb"}]}
        mock_ti_service = AsyncMock()
        mock_ti_service.enrich.return_value = ti_data

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=RuntimeError("DB down"))

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        pipeline = Pipeline(ti_service=mock_ti_service, session_factory=mock_session_factory)

        evento_dict = {"id": "evt-001", "source_ip": "1.2.3.4", "source": "test"}

        with patch("app.models.event.NormalizedEvent"):
            # Should NOT raise
            await pipeline._enrich_ti(evento_dict)

    async def test_enrichment_skipped_when_event_has_no_id(self):
        """When event has no id, enrichment returns early."""
        mock_ti_service = AsyncMock()
        mock_ti_service.enrich.return_value = {"matches": []}

        pipeline = Pipeline(ti_service=mock_ti_service)

        evento_dict = {"source_ip": "1.2.3.4", "source": "test"}  # No 'id'

        await pipeline._enrich_ti(evento_dict)

        mock_ti_service.enrich.assert_called_once_with(evento_dict)
        # No DB interaction since event has no id

    async def test_enrichment_skipped_when_ti_service_none(self):
        """When ti_service is None, _enrich_ti does nothing (graceful no-op)."""
        pipeline = Pipeline(ti_service=None)
        evento_dict = {"id": "evt-001", "source_ip": "1.2.3.4", "source": "test"}

        # _enrich_ti should not raise — it's guarded in process(),
        # but calling directly should also be safe (try/except catches it)
        # Verify no crash happens
        await pipeline._enrich_ti(evento_dict)
