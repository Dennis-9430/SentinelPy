"""Additional coverage tests for analysis_service.py.

Covers: EntityRiskStore (load_from_db, get_or_create, update_risk w/ decay,
persist errors, get_all_risks), AnalysisService (init_async ML failure,
ensure_entity_risks_table error, seed_baselines, analyze w/ disabled/error,
_compute_event_zscores, _persist_analysis_data, _update_entity_risk,
get_anomalies, get_risks, shutdown, grouping_loop).

All tests use mocks for DB — no Docker required.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.services.analysis_service import (
    AnalysisService,
    EntityRiskStore,
)

# ── Mock helpers ─────────────────────────────────────────────────────────


def _make_mock_row(entity_key="test-entity", risk_score=0.5, updated_at=None):
    """Create a mock DB row for entity_risks (index-based access)."""
    data = [entity_key, risk_score, updated_at or datetime.now(UTC)]

    class _Row:
        def __getitem__(self, idx):
            return data[idx]

    return _Row()


def _make_mock_event_row(
    ev_id="00000000-0000-0000-0000-000000000001",
    source="test-src",
    collector_type="syslog",
    event_type="auth_failure",
    severity="high",
    description="test event",
    source_ip="10.0.0.1",
    destination_ip="10.0.0.2",
    source_port=8080,
    destination_port=443,
    user_name="admin",
    event_timestamp=None,
    analysis_data=None,
):
    """Create a mock DB row for events table queries (index-based access)."""
    ts = event_timestamp or datetime.now(UTC)
    data = [
        ev_id,
        source,
        collector_type,
        event_type,
        severity,
        description,
        source_ip,
        destination_ip,
        source_port,
        destination_port,
        user_name,
        ts,
        analysis_data,
    ]

    class _Row:
        def __getitem__(self, idx):
            return data[idx]

    return _Row()


def _make_session_factory(session):
    """Create a mock session factory that returns an async context manager.

    The source code does: `async with self._session_factory() as session:`
    So factory() must return an object with __aenter__ / __aexit__.
    """
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


# ══════════════════════════════════════════════════════════════════════════
# EntityRiskStore
# ══════════════════════════════════════════════════════════════════════════


class TestEntityRiskStore:
    """EntityRiskStore with mocked DB."""

    @pytest.mark.asyncio
    async def test_load_from_db_populates_risks(self):
        """load_from_db reads persisted rows into memory."""
        now = datetime.now(UTC)
        rows = [_make_mock_row("10.0.0.99", 0.75, now)]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        factory = _make_session_factory(mock_session)
        store = EntityRiskStore(factory)
        await store.load_from_db()

        assert "10.0.0.99" in store._risks
        assert store._risks["10.0.0.99"] == pytest.approx(0.75)
        assert store._timestamps["10.0.0.99"] == now

    @pytest.mark.asyncio
    async def test_load_from_db_multiple_rows(self):
        """load_from_db handles multiple rows."""
        now = datetime.now(UTC)
        rows = [
            _make_mock_row("10.0.0.1", 0.5, now),
            _make_mock_row("10.0.0.2", 0.8, now),
            _make_mock_row("10.0.0.3", 0.2, now),
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        factory = _make_session_factory(mock_session)
        store = EntityRiskStore(factory)
        await store.load_from_db()

        assert len(store._risks) == 3
        assert store._risks["10.0.0.2"] == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_load_from_db_logs_info_when_rows_exist(self):
        """load_from_db logs info when rows are loaded."""
        rows = [_make_mock_row("10.0.0.99", 0.75)]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        factory = _make_session_factory(mock_session)
        store = EntityRiskStore(factory)
        with patch("app.services.analysis_service.logger") as mock_logger:
            await store.load_from_db()
            mock_logger.info.assert_called_once_with(
                "Riesgos cargados desde DB: %d entidades", 1
            )

    @pytest.mark.asyncio
    async def test_load_from_db_empty(self):
        """load_from_db with no rows succeeds silently."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        factory = _make_session_factory(mock_session)
        store = EntityRiskStore(factory)
        await store.load_from_db()
        assert len(store._risks) == 0

    @pytest.mark.asyncio
    async def test_load_from_db_exception_logs_warning(self):
        """load_from_db logs warning on DB error."""
        factory = _make_broken_factory("db down")
        store = EntityRiskStore(factory)
        with patch("app.services.analysis_service.logger") as mock_logger:
            await store.load_from_db()
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_create_creates_new(self):
        """get_or_create creates entity with score 0.0 when new."""
        mock_session = AsyncMock()
        factory = _make_session_factory(mock_session)

        store = EntityRiskStore(factory)
        await store.load_from_db()

        score = await store.get_or_create("new-entity")
        assert score == 0.0
        assert "new-entity" in store._risks

    @pytest.mark.asyncio
    async def test_get_or_create_existing(self):
        """get_or_create returns existing score."""
        mock_session = AsyncMock()
        factory = _make_session_factory(mock_session)

        store = EntityRiskStore(factory)
        store._risks["existing"] = 0.5
        store._timestamps["existing"] = datetime.now(UTC)

        score = await store.get_or_create("existing")
        assert score == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_update_risk_applies_decay(self):
        """update_risk applies exponential decay when time has passed."""
        mock_session = AsyncMock()
        factory = _make_session_factory(mock_session)

        store = EntityRiskStore(factory)
        store._risks["decay-entity"] = 0.8
        store._timestamps["decay-entity"] = datetime.now(UTC) - timedelta(hours=1)

        new_score = await store.update_risk("decay-entity", 0.1)
        assert new_score < 0.9
        assert new_score > 0.0

    @pytest.mark.asyncio
    async def test_update_risk_no_decay_when_no_timestamp(self):
        """update_risk skips decay when entity has no timestamp."""
        mock_session = AsyncMock()
        factory = _make_session_factory(mock_session)

        store = EntityRiskStore(factory)
        store._risks["no-ts"] = 0.5

        new_score = await store.update_risk("no-ts", 0.2)
        assert new_score == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_persist_error_logs_and_does_not_raise(self):
        """_persist logs error on failure without crashing."""
        factory = _make_broken_factory("persist fail")
        store = EntityRiskStore(factory)
        store._timestamps["fail-key"] = datetime.now(UTC)

        with patch("app.services.analysis_service.logger") as mock_logger:
            await store._persist("fail-key", 0.9)
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_risks_sorted_desc(self):
        """get_all_risks returns risks sorted by score descending."""
        store = EntityRiskStore(MagicMock())
        now = datetime.now(UTC)
        store._risks = {"low": 0.1, "high": 0.9, "mid": 0.5}
        store._timestamps = {"low": now, "high": now, "mid": now}

        all_risks = store.get_all_risks()
        scores = [r["risk_score"] for r in all_risks]
        assert scores == sorted(scores, reverse=True)
        assert all_risks[0]["entity_key"] == "high"

    @pytest.mark.asyncio
    async def test_get_all_risks_empty(self):
        store = EntityRiskStore(MagicMock())
        assert store.get_all_risks() == []

    @pytest.mark.asyncio
    async def test_get_all_risks_includes_timestamp(self):
        now = datetime.now(UTC)
        store = EntityRiskStore(MagicMock())
        store._risks = {"ent": 0.5}
        store._timestamps = {"ent": now}

        all_risks = store.get_all_risks()
        assert all_risks[0]["updated_at"] == now


# ══════════════════════════════════════════════════════════════════════════
# AnalysisService — init_async, seed_baselines, ensure_table
# ══════════════════════════════════════════════════════════════════════════


class TestAnalysisServiceInit:
    """Tests for AnalysisService initialization paths."""

    @pytest.mark.asyncio
    async def test_init_async_creates_store_and_loads(self):
        """init_async creates entity_risks table and loads baselines."""
        mock_session = AsyncMock()
        factory = _make_session_factory(mock_session)

        svc = AnalysisService(factory)
        with (
            patch.object(svc, "seed_baselines", new_callable=AsyncMock),
            patch("app.services.analysis_service.MLEngine") as MockML,
        ):
            mock_ml = MagicMock()
            mock_ml.init_async = AsyncMock()
            MockML.return_value = mock_ml
            await svc.init_async()

        assert svc._risk_store is not None

    @pytest.mark.asyncio
    async def test_init_async_ml_failure_sets_none(self):
        """init_async sets _ml_engine to None when ML init fails."""
        mock_session = AsyncMock()
        factory = _make_session_factory(mock_session)

        svc = AnalysisService(factory)
        with (
            patch.object(svc, "seed_baselines", new_callable=AsyncMock),
            patch(
                "app.services.analysis_service.MLEngine",
                side_effect=RuntimeError("ml deps missing"),
            ),
        ):
            await svc.init_async()

        assert svc._ml_engine is None

    @pytest.mark.asyncio
    async def test_init_async_ml_init_error_logs_warning(self):
        """init_async logs warning when ML init_async fails."""
        mock_session = AsyncMock()
        factory = _make_session_factory(mock_session)

        svc = AnalysisService(factory)
        with (
            patch.object(svc, "seed_baselines", new_callable=AsyncMock),
            patch("app.services.analysis_service.MLEngine") as MockML,
            patch("app.services.analysis_service.logger") as mock_logger,
        ):
            mock_ml = MagicMock()
            mock_ml.init_async = AsyncMock(side_effect=RuntimeError("ml fail"))
            MockML.return_value = mock_ml
            await svc.init_async()
            mock_logger.warning.assert_called()

        assert svc._ml_engine is None

    @pytest.mark.asyncio
    async def test_ensure_entity_risks_table_error_logs(self):
        """_ensure_entity_risks_table logs warning on error."""
        factory = _make_broken_factory("table fail")
        svc = AnalysisService(factory)
        with patch("app.services.analysis_service.logger") as mock_logger:
            await svc._ensure_entity_risks_table()
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_seed_baselines_with_enough_events(self):
        """seed_baselines computes baselines from recent events."""
        mock_events = []
        for i in range(15):
            ev = MagicMock()
            ev.source_port = 8080 + i
            ev.destination_port = 443
            ev.event_count = None
            ev.duration = None
            ev.bytes_sent = None
            ev.bytes_received = None
            mock_events.append(ev)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_events
        mock_session.execute.return_value = mock_result

        factory = _make_session_factory(mock_session)
        svc = AnalysisService(factory)
        await svc.seed_baselines()

        assert "source_port" in svc._baselines
        assert "destination_port" in svc._baselines

    @pytest.mark.asyncio
    async def test_seed_baselines_no_events(self):
        """seed_baselines with no events leaves baselines empty."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        factory = _make_session_factory(mock_session)
        svc = AnalysisService(factory)
        await svc.seed_baselines()
        assert len(svc._baselines) == 0

    @pytest.mark.asyncio
    async def test_seed_baselines_not_enough_values_per_field(self):
        """seed_baselines skips fields with < 10 values."""
        mock_events = []
        for _ in range(5):
            ev = MagicMock()
            ev.source_port = 8080
            ev.destination_port = None
            ev.event_count = None
            ev.duration = None
            ev.bytes_sent = None
            ev.bytes_received = None
            mock_events.append(ev)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_events
        mock_session.execute.return_value = mock_result

        factory = _make_session_factory(mock_session)
        svc = AnalysisService(factory)
        await svc.seed_baselines()
        assert len(svc._baselines) == 0

    @pytest.mark.asyncio
    async def test_seed_baselines_exception_logs_error(self):
        """seed_baselines logs error on exception."""
        factory = _make_broken_factory("seed fail")
        svc = AnalysisService(factory)
        with patch("app.services.analysis_service.logger") as mock_logger:
            await svc.seed_baselines()
            mock_logger.error.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════
# AnalysisService — analyze
# ══════════════════════════════════════════════════════════════════════════


class TestAnalysisServiceAnalyze:
    """Tests for the analyze method."""

    @pytest.mark.asyncio
    async def test_analyze_returns_when_disabled(self):
        """analyze returns immediately when analysis_enabled=False."""
        svc = AnalysisService(MagicMock())
        svc._risk_store = MagicMock()

        with patch.object(settings, "analysis_enabled", False):
            await svc.analyze("fake-id", {"severity": "high"})

    @pytest.mark.asyncio
    async def test_analyze_exception_handled(self):
        """analyze catches exceptions and logs them."""
        svc = AnalysisService(MagicMock())
        svc._risk_store = MagicMock()

        with (
            patch.object(settings, "analysis_enabled", True),
            patch.object(
                svc,
                "_compute_event_zscores",
                side_effect=RuntimeError("boom"),
            ),
            patch("app.services.analysis_service.logger") as mock_logger,
        ):
            await svc.analyze("fake-id", {"severity": "high"})
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_with_zscores(self):
        """analyze computes z-scores and persists analysis_data."""
        mock_event = MagicMock()
        mock_event.id = "test-event-id"

        # First call: _persist_analysis_data queries the event
        # We need the factory to return a session that can find the event
        mock_session = AsyncMock()
        mock_find_result = MagicMock()
        mock_find_result.scalar_one_or_none.return_value = mock_event
        mock_session.execute.return_value = mock_find_result
        mock_session.commit = AsyncMock()

        factory = _make_session_factory(mock_session)

        svc = AnalysisService(factory)
        svc._baselines = {"source_port": {"mean": 8080.0, "std": 10.0, "count": 100}}
        svc._risk_store = MagicMock()
        svc._risk_store.update_risk = AsyncMock(return_value=0.5)

        with patch.object(settings, "analysis_enabled", True):
            await svc.analyze(
                "test-event-id", {"source_port": 8100, "severity": "high"}
            )

        # Verify persist was called
        assert mock_event.analysis_data is not None
        assert "zscores" in mock_event.analysis_data

    @pytest.mark.asyncio
    async def test_analyze_with_ml_score(self):
        """analyze includes ml_score when ML engine is available."""
        mock_event = MagicMock()
        mock_event.id = "test-event-id"

        mock_session = AsyncMock()
        mock_find_result = MagicMock()
        mock_find_result.scalar_one_or_none.return_value = mock_event
        mock_session.execute.return_value = mock_find_result
        mock_session.commit = AsyncMock()

        factory = _make_session_factory(mock_session)

        svc = AnalysisService(factory)
        svc._baselines = {}
        mock_ml = MagicMock()
        mock_ml.available = True
        mock_ml.score = AsyncMock(return_value=-0.5)
        svc._ml_engine = mock_ml
        svc._risk_store = MagicMock()
        svc._risk_store.update_risk = AsyncMock(return_value=0.1)

        with patch.object(settings, "analysis_enabled", True):
            await svc.analyze("test-event-id", {"severity": "info"})

        assert mock_event.analysis_data is not None
        assert "ml_score" in mock_event.analysis_data

    @pytest.mark.asyncio
    async def test_analyze_no_analysis_data_when_empty(self):
        """analyze doesn't persist when no z-scores and no ml_score."""
        mock_session = AsyncMock()
        factory = _make_session_factory(mock_session)

        svc = AnalysisService(factory)
        svc._baselines = {}
        svc._ml_engine = None
        svc._risk_store = MagicMock()
        svc._risk_store.update_risk = AsyncMock(return_value=0.0)

        with patch.object(settings, "analysis_enabled", True):
            await svc.analyze("fake-id", {"severity": "info"})

        # No persist call when analysis_data is empty
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_analyze_persist_event_not_found(self):
        """analyze handles persist when event not found."""
        mock_session = AsyncMock()
        mock_find_result = MagicMock()
        mock_find_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_find_result

        factory = _make_session_factory(mock_session)

        svc = AnalysisService(factory)
        svc._baselines = {"source_port": {"mean": 8080.0, "std": 10.0, "count": 100}}
        svc._risk_store = MagicMock()
        svc._risk_store.update_risk = AsyncMock(return_value=0.5)

        with patch.object(settings, "analysis_enabled", True):
            await svc.analyze("missing-id", {"source_port": 8100, "severity": "high"})

        # Event not found → no add/commit
        mock_session.add.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# AnalysisService — _compute_event_zscores
# ══════════════════════════════════════════════════════════════════════════


class TestComputeEventZscores:
    """Tests for z-score computation on events."""

    def test_no_baselines_returns_empty(self):
        svc = AnalysisService(MagicMock())
        svc._baselines = {}
        assert svc._compute_event_zscores({"source_port": 8080}) == {}

    def test_anomalous_zscore_included(self):
        svc = AnalysisService(MagicMock())
        svc._baselines = {
            "source_port": {"mean": 8080.0, "std": 10.0, "count": 100},
        }
        result = svc._compute_event_zscores({"source_port": 8100})
        assert "source_port" in result
        assert result["source_port"] == pytest.approx(2.0)

    def test_normal_zscore_excluded(self):
        svc = AnalysisService(MagicMock())
        svc._baselines = {
            "source_port": {"mean": 8080.0, "std": 10.0, "count": 100},
        }
        result = svc._compute_event_zscores({"source_port": 8085})
        assert result == {}

    def test_baseline_with_zero_std_skipped(self):
        svc = AnalysisService(MagicMock())
        svc._baselines = {
            "source_port": {"mean": 8080.0, "std": 0.0, "count": 100},
        }
        result = svc._compute_event_zscores({"source_port": 8100})
        assert result == {}

    def test_multiple_fields(self):
        svc = AnalysisService(MagicMock())
        svc._baselines = {
            "source_port": {"mean": 8080.0, "std": 10.0, "count": 100},
            "destination_port": {"mean": 443.0, "std": 5.0, "count": 100},
        }
        result = svc._compute_event_zscores(
            {"source_port": 8100, "destination_port": 460}
        )
        assert "source_port" in result
        assert "destination_port" in result

    def test_negative_zscore_included(self):
        svc = AnalysisService(MagicMock())
        svc._baselines = {
            "source_port": {"mean": 8080.0, "std": 10.0, "count": 100},
        }
        result = svc._compute_event_zscores({"source_port": 8050})
        assert "source_port" in result
        assert result["source_port"] == pytest.approx(-3.0)


# ══════════════════════════════════════════════════════════════════════════
# AnalysisService — _persist_analysis_data
# ══════════════════════════════════════════════════════════════════════════


class TestPersistAnalysisData:
    """Tests for persisting analysis data to events."""

    @pytest.mark.asyncio
    async def test_persist_analysis_data_success(self):
        mock_event = MagicMock()
        mock_event.id = "evt-1"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_event
        mock_session.execute.return_value = mock_result

        factory = _make_session_factory(mock_session)
        svc = AnalysisService(factory)

        await svc._persist_analysis_data("evt-1", {"zscores": {"source_port": 3.0}})

        mock_session.add.assert_called_once_with(mock_event)
        mock_session.commit.assert_called_once()
        assert mock_event.analysis_data == {"zscores": {"source_port": 3.0}}

    @pytest.mark.asyncio
    async def test_persist_analysis_data_event_not_found(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        factory = _make_session_factory(mock_session)
        svc = AnalysisService(factory)

        await svc._persist_analysis_data("missing", {"zscores": {}})
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_analysis_data_exception_logged(self):
        factory = _make_broken_factory("db fail")
        svc = AnalysisService(factory)
        with patch("app.services.analysis_service.logger") as mock_logger:
            await svc._persist_analysis_data("fake-id", {"zscores": {}})
            mock_logger.error.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════
# AnalysisService — _update_entity_risk
# ══════════════════════════════════════════════════════════════════════════


class TestUpdateEntityRisk:
    """Tests for entity risk update logic."""

    @pytest.mark.asyncio
    async def test_no_risk_store_returns_early(self):
        svc = AnalysisService(MagicMock())
        svc._risk_store = None
        await svc._update_entity_risk({"source_ip": "10.0.0.1"})

    @pytest.mark.asyncio
    async def test_no_entity_key_returns_early(self):
        svc = AnalysisService(MagicMock())
        svc._risk_store = MagicMock()
        await svc._update_entity_risk({"severity": "high"})
        svc._risk_store.update_risk.assert_not_called()

    @pytest.mark.asyncio
    async def test_entity_from_source_ip(self):
        svc = AnalysisService(MagicMock())
        mock_store = MagicMock()
        mock_store.update_risk = AsyncMock(return_value=0.5)
        svc._risk_store = mock_store

        await svc._update_entity_risk({"source_ip": "10.0.0.1", "severity": "critical"})
        mock_store.update_risk.assert_called_once_with("10.0.0.1", 0.15)

    @pytest.mark.asyncio
    async def test_entity_from_user_name(self):
        svc = AnalysisService(MagicMock())
        mock_store = MagicMock()
        mock_store.update_risk = AsyncMock(return_value=0.1)
        svc._risk_store = mock_store

        await svc._update_entity_risk({"user_name": "admin", "severity": "medium"})
        mock_store.update_risk.assert_called_once_with("admin", 0.05)

    @pytest.mark.asyncio
    async def test_entity_from_source_fallback(self):
        svc = AnalysisService(MagicMock())
        mock_store = MagicMock()
        mock_store.update_risk = AsyncMock(return_value=0.01)
        svc._risk_store = mock_store

        await svc._update_entity_risk({"source": "syslog-01", "severity": "info"})
        mock_store.update_risk.assert_called_once_with("syslog-01", 0.01)

    @pytest.mark.asyncio
    async def test_unknown_severity_uses_default_increment(self):
        svc = AnalysisService(MagicMock())
        mock_store = MagicMock()
        mock_store.update_risk = AsyncMock(return_value=0.01)
        svc._risk_store = mock_store

        await svc._update_entity_risk({"source_ip": "10.0.0.1", "severity": "unknown"})
        mock_store.update_risk.assert_called_once_with("10.0.0.1", 0.01)

    @pytest.mark.asyncio
    async def test_entity_priority_source_ip_over_user(self):
        svc = AnalysisService(MagicMock())
        mock_store = MagicMock()
        mock_store.update_risk = AsyncMock(return_value=0.1)
        svc._risk_store = mock_store

        await svc._update_entity_risk(
            {"source_ip": "10.0.0.1", "user_name": "admin", "severity": "high"}
        )
        mock_store.update_risk.assert_called_once_with("10.0.0.1", 0.10)


# ══════════════════════════════════════════════════════════════════════════
# AnalysisService — get_anomalies, get_risks
# ══════════════════════════════════════════════════════════════════════════


class TestGetAnomalies:
    """Tests for get_anomalies query."""

    @pytest.mark.asyncio
    async def test_get_anomalies_returns_data(self):
        ts = datetime.now(UTC)
        row = _make_mock_event_row(event_timestamp=ts)
        count_row = MagicMock()
        count_row.scalar.return_value = 1

        rows_result = MagicMock()
        rows_result.fetchall.return_value = [row]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[rows_result, count_row])

        factory = _make_session_factory(mock_session)
        svc = AnalysisService(factory)

        anomalies, total = await svc.get_anomalies()
        assert len(anomalies) == 1
        assert total == 1
        assert anomalies[0]["source"] == "test-src"

    @pytest.mark.asyncio
    async def test_get_anomalies_empty(self):
        empty_result = MagicMock()
        empty_result.fetchall.return_value = []
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[empty_result, count_result])

        factory = _make_session_factory(mock_session)
        svc = AnalysisService(factory)

        anomalies, total = await svc.get_anomalies()
        assert anomalies == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_anomalies_exception_returns_empty(self):
        factory = _make_broken_factory("query fail")
        svc = AnalysisService(factory)
        with patch("app.services.analysis_service.logger"):
            anomalies, total = await svc.get_anomalies()
        assert anomalies == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_anomalies_description_truncated(self):
        """Description is truncated to 200 chars."""
        ts = datetime.now(UTC)
        row = _make_mock_event_row(description="A" * 300, event_timestamp=ts)

        count_row = MagicMock()
        count_row.scalar.return_value = 1
        rows_result = MagicMock()
        rows_result.fetchall.return_value = [row]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[rows_result, count_row])

        factory = _make_session_factory(mock_session)
        svc = AnalysisService(factory)

        anomalies, total = await svc.get_anomalies()
        assert len(anomalies[0]["description"]) == 200


class TestGetRisks:
    """Tests for get_risks query."""

    @pytest.mark.asyncio
    async def test_get_risks_no_store_returns_empty(self):
        svc = AnalysisService(MagicMock())
        svc._risk_store = None
        risks, total = await svc.get_risks()
        assert risks == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_risks_with_data(self):
        svc = AnalysisService(MagicMock())
        mock_store = MagicMock()
        mock_store.get_all_risks.return_value = [
            {"entity_key": "a", "risk_score": 0.5, "updated_at": datetime.now(UTC)},
            {"entity_key": "b", "risk_score": 0.3, "updated_at": datetime.now(UTC)},
        ]
        svc._risk_store = mock_store

        risks, total = await svc.get_risks()
        assert total == 2
        assert len(risks) == 2

    @pytest.mark.asyncio
    async def test_get_risks_pagination(self):
        svc = AnalysisService(MagicMock())
        mock_store = MagicMock()
        mock_store.get_all_risks.return_value = [
            {"entity_key": f"ent-{i}", "risk_score": 0.1 * (i + 1)} for i in range(5)
        ]
        svc._risk_store = mock_store

        risks, total = await svc.get_risks(limit=2, offset=0)
        assert len(risks) == 2
        assert total == 5


# ══════════════════════════════════════════════════════════════════════════
# AnalysisService — shutdown
# ══════════════════════════════════════════════════════════════════════════


class TestShutdown:
    """Tests for shutdown method."""

    @pytest.mark.asyncio
    async def test_shutdown_cancels_grouping_task(self):
        svc = AnalysisService(MagicMock())

        async def _noop():
            await asyncio.sleep(100)

        svc._grouping_task = asyncio.create_task(_noop())
        svc._ml_engine = None

        await svc.shutdown()
        assert svc._grouping_task.cancelled()

    @pytest.mark.asyncio
    async def test_shutdown_without_task(self):
        svc = AnalysisService(MagicMock())
        svc._ml_engine = None
        await svc.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_calls_ml_shutdown(self):
        svc = AnalysisService(MagicMock())
        svc._grouping_task = None
        mock_ml = MagicMock()
        mock_ml.shutdown = AsyncMock()
        svc._ml_engine = mock_ml

        await svc.shutdown()
        mock_ml.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_no_ml_engine(self):
        svc = AnalysisService(MagicMock())
        svc._grouping_task = None
        svc._ml_engine = None
        await svc.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_with_none_grouping_task(self):
        svc = AnalysisService(MagicMock())
        svc._ml_engine = None
        svc._grouping_task = None
        await svc.shutdown()


# ══════════════════════════════════════════════════════════════════════════
# AnalysisService — _grouping_loop
# ══════════════════════════════════════════════════════════════════════════


class TestGroupingLoop:
    """Tests for the background grouping loop."""

    @pytest.mark.asyncio
    async def test_grouping_loop_cancels_gracefully(self):
        """_grouping_loop exits on CancelledError."""
        svc = AnalysisService(MagicMock())

        async def _cancel_sleep(_):
            raise asyncio.CancelledError()

        with (
            patch("app.services.analysis_service.asyncio.sleep", _cancel_sleep),
            patch("app.services.analysis_service.logger"),
        ):
            await svc._grouping_loop()

    @pytest.mark.asyncio
    async def test_grouping_loop_logs_error_on_exception(self):
        """_grouping_loop catches general exceptions and logs them."""
        svc = AnalysisService(MagicMock())
        # Make the session factory fail with a recognizable error
        svc._session_factory = MagicMock()
        svc._session_factory.return_value.__aenter__ = AsyncMock(
            side_effect=RuntimeError("session factory error")
        )
        svc._session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        call_count = 0

        async def _sleep_then_cancel(_):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return  # First sleep succeeds → enters loop body
            raise asyncio.CancelledError()  # Second sleep (in except block) cancels

        with (
            patch("app.services.analysis_service.asyncio.sleep", _sleep_then_cancel),
            patch("app.services.analysis_service.logger") as mock_logger,
        ):
            with pytest.raises(asyncio.CancelledError):
                await svc._grouping_loop()
            error_calls = [
                c
                for c in mock_logger.error.call_args_list
                if "Error in grouping task" in str(c)
            ]
            assert len(error_calls) >= 1
