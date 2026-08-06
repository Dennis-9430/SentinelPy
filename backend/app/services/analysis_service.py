"""Statistical analysis and risk scoring service.

Implements:
  - Z-score baselines for anomaly detection
  - Entity risk scoring with exponential decay
  - ML inference (IsolationForest) when available (Slice 3)

All analysis operations are non-blocking (fire-and-forget).
"""

import asyncio
import contextlib
import logging
import math
import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.services.ml_engine import MLEngine

logger = logging.getLogger(__name__)

# ── Analysis constants ─────────────────────────────────────────────────────

CAMPOS_NUMERICOS = [
    "source_port",
    "destination_port",
    "event_count",
    "duration",
    "bytes_sent",
    "bytes_received",
]

# ═══════════════════════════════════════════════════════════════════════════
# Pure functions (testable without DB or mocks)
# ═══════════════════════════════════════════════════════════════════════════


def _is_numeric(valor: Any) -> bool:
    """Checks whether a value is numeric (int or float, not bool).

    Args:
        valor: Value to check.

    Returns:
        True if it is an int or float (not bool).
    """
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _compute_baseline_stats(valores: list[float]) -> tuple[float, float]:
    """Computes the mean and population standard deviation of a list of values.

    Uses ddof=1 (sample standard deviation) for a better estimate.

    Args:
        valores: List of floats.

    Returns:
        Tuple (mean, std). If the list is empty, returns (0.0, 0.0).
    """
    if not valores:
        return 0.0, 0.0
    if len(valores) < 2:
        return float(valores[0]), 0.0
    mean = statistics.mean(valores)
    std = statistics.stdev(valores)
    return mean, std


def _extract_numeric_fields(evento: dict) -> dict[str, float]:
    """Extracts relevant numeric fields from an event.

    Only keeps fields defined in CAMPOS_NUMERICOS that have
    non-None numeric values.

    Args:
        evento: Dict with event data.

    Returns:
        Dict with {field: numeric_value}.
    """
    result = {}
    for campo in CAMPOS_NUMERICOS:
        valor = evento.get(campo)
        if _is_numeric(valor):
            result[campo] = float(valor)
    return result


def _compute_zscore(value: float, mean: float, std: float) -> float | None:
    """Computes the z-score of a value against a baseline.

    Formula: z = (value - mean) / std

    Args:
        value: Value to evaluate.
        mean: Mean of the baseline.
        std: Standard deviation of the baseline.

    Returns:
        Z-score as a float, or None if std <= 0 (no variation).
    """
    if std <= 0:
        return None
    return (value - mean) / std


def _increment_risk(current: float, increment: float, max_risk: float) -> float:
    """Increments a risk score with a cap at max_risk.

    Args:
        current: Current score (0.0 to max_risk).
        increment: Increment to apply.
        max_risk: Maximum allowed value.

    Returns:
        Incremented score, capped at max_risk.
    """
    nuevo = current + increment
    return min(nuevo, max_risk)


def _decay_risk(score: float, decay_rate: float, elapsed_seconds: float) -> float:
    """Applies exponential decay to a risk score.

    Formula: score * exp(-decay_rate * elapsed_hours)

    Where elapsed_hours = elapsed_seconds / 3600.

    Args:
        score: Current score to decay.
        decay_rate: Decay rate (e.g. 0.5 = halve per hour).
        elapsed_seconds: Seconds elapsed since the last update.

    Returns:
        Decayed score.
    """
    if score <= 0 or decay_rate <= 0 or elapsed_seconds <= 0:
        return score
    elapsed_hours = elapsed_seconds / 3600.0
    return score * math.exp(-decay_rate * elapsed_hours)


# ═══════════════════════════════════════════════════════════════════════════
# Entity Risk
# ═══════════════════════════════════════════════════════════════════════════


class EntityRiskStore:
    """Per-entity risk store with write-through to the DB.

    Keeps an in-memory dict for fast reads and persists
    each update to the entity_risks table.

    Risks are identified by entity_key (e.g. IP, username).
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self._risks: dict[str, float] = {}
        self._timestamps: dict[str, datetime] = {}

    async def load_from_db(self):
        """Loads all risks from the DB at startup."""
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    text("SELECT entity_key, risk_score, updated_at FROM entity_risks")
                )
                rows = result.fetchall()
                for row in rows:
                    self._risks[row[0]] = float(row[1])
                    self._timestamps[row[0]] = row[2]
                if rows:
                    logger.info("Risks loaded from DB: %d entities", len(rows))
        except Exception as e:
            logger.warning("Could not load risks from DB: %s", e)

    async def get_or_create(self, entity_key: str) -> float:
        """Gets the current risk of an entity.

        If it does not exist, creates it with score 0.0 and persists it.

        Args:
            entity_key: Unique key of the entity.

        Returns:
            Current risk score (float).
        """
        if entity_key not in self._risks:
            self._risks[entity_key] = 0.0
            self._timestamps[entity_key] = datetime.now(UTC)
            await self._persist(entity_key, 0.0)
        return self._risks[entity_key]

    async def update_risk(self, entity_key: str, increment: float) -> float:
        """Increments an entity's risk with write-through.

        Applies decay first if time has passed since the last update,
        then applies the increment with a cap at max_risk.

        Args:
            entity_key: Unique key of the entity.
            increment: How much to increment.

        Returns:
            New score after the increment.
        """
        ahora = datetime.now(UTC)
        current = self._risks.get(entity_key, 0.0)

        # Apply decay if time has passed
        if entity_key in self._timestamps:
            elapsed = (ahora - self._timestamps[entity_key]).total_seconds()
            if elapsed > 0:
                current = _decay_risk(current, settings.analysis_decay_rate, elapsed)

        nuevo = _increment_risk(current, increment, settings.analysis_max_risk)

        self._risks[entity_key] = nuevo
        self._timestamps[entity_key] = ahora
        await self._persist(entity_key, nuevo)
        return nuevo

    async def _persist(self, entity_key: str, score: float):
        """Persists a risk score in the entity_risks table.

        Uses INSERT ... ON CONFLICT DO UPDATE (upsert).
        """
        try:
            async with self._session_factory() as session:
                await session.execute(
                    text(
                        """INSERT INTO entity_risks (entity_key, risk_score, updated_at)
                           VALUES (:key, :score, :ts)
                           ON CONFLICT (entity_key)
                           DO UPDATE SET risk_score = :score2, updated_at = :ts2"""
                    ),
                    {
                        "key": entity_key,
                        "score": score,
                        "ts": self._timestamps[entity_key],
                        "score2": score,
                        "ts2": self._timestamps[entity_key],
                    },
                )
                await session.commit()
        except Exception as e:
            logger.error("Error persisting risk for %s: %s", entity_key, e)

    def get_all_risks(self) -> list[dict]:
        """Returns all in-memory risks for querying.

        Returns:
            List of dicts with entity_key, risk_score, updated_at.
        """
        return [
            {
                "entity_key": key,
                "risk_score": score,
                "updated_at": self._timestamps.get(key),
            }
            for key, score in sorted(
                self._risks.items(), key=lambda x: x[1], reverse=True
            )
        ]


# ═══════════════════════════════════════════════════════════════════════════
# AnalysisService
# ═══════════════════════════════════════════════════════════════════════════


class AnalysisService:
    """Statistical event analysis service.

    Keeps in-memory baselines (mean/std per field) seeded from the DB,
    computes z-scores per event, and updates per-entity risks.

    Flow:
        1. On startup, seed baselines from the DB (query the last N events)
        2. For each incoming event, compute z-scores + update risk
        3. Results are persisted in event.analysis_data and entity_risks
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self._baselines: dict[str, dict] = {}
        # entity_risk_store se inicializa en init_async
        self._risk_store: EntityRiskStore | None = None
        # ML engine (optional — graceful fallback if deps missing)
        self._ml_engine: Any | None = None

    async def init_async(self):
        """Initializes the service: creates the entity_risks table, loads risks and baselines.

        Must be called after creating the instance, in the app lifespan.
        """
        # Make sure the entity_risks table exists
        await self._ensure_entity_risks_table()

        # Initialize risk store
        self._risk_store = EntityRiskStore(self._session_factory)
        await self._risk_store.load_from_db()

        # Seed baselines
        await self.seed_baselines()

        # Initialize ML engine (optional — graceful fallback if deps missing)
        try:
            self._ml_engine = MLEngine(self._session_factory)
            await self._ml_engine.init_async()
        except Exception as e:
            logger.warning("ML engine init failed: %s", e)
            self._ml_engine = None

        # Start background grouping task
        await self._start_grouping_task()

        logger.info("AnalysisService initialized")

    async def _ensure_entity_risks_table(self):
        """Creates the entity_risks table if it does not exist."""
        try:
            async with self._session_factory() as session:
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
        except Exception as e:
            logger.warning("Error creating entity_risks table: %s", e)

    # ── Baseline management ───────────────────────────────────────────────

    async def seed_baselines(self):
        """Seeds baselines from the database.

        Queries the last N events (ANALYSIS_BASELINE_WINDOW_MINUTES)
        and computes mean/std for each numeric field.

        If there is not enough data, baselines stay empty
        and are computed as events arrive.
        """
        try:
            async with self._session_factory() as session:
                from app.models.event import NormalizedEvent

                # Compute the window timestamp
                desde = datetime.now(UTC) - (
                    timedelta(minutes=settings.analysis_baseline_window_minutes)
                )

                result = await session.execute(
                    select(NormalizedEvent)
                    .where(NormalizedEvent.event_timestamp >= desde)
                    .order_by(NormalizedEvent.event_timestamp.desc())
                )
                eventos = result.scalars().all()

                if not eventos:
                    logger.info(
                        "No events in the baseline window (%d min)",
                        settings.analysis_baseline_window_minutes,
                    )
                    return

                # Group values by field
                valores_por_campo: dict[str, list[float]] = {}
                for ev in eventos:
                    for campo in CAMPOS_NUMERICOS:
                        valor = getattr(ev, campo, None)
                        if _is_numeric(valor):
                            valores_por_campo.setdefault(campo, []).append(float(valor))

                # Compute statistics per field
                for campo, valores in valores_por_campo.items():
                    if len(valores) >= 10:  # minimum 10 values for a baseline
                        mean, std = _compute_baseline_stats(valores)
                        self._baselines[campo] = {
                            "mean": mean,
                            "std": std,
                            "count": len(valores),
                        }
                        logger.debug(
                            "Baseline %s: mean=%.2f, std=%.2f (n=%d)",
                            campo,
                            mean,
                            std,
                            len(valores),
                        )

                logger.info(
                    "Baselines seeded: %d fields with enough data",
                    len(self._baselines),
                )

        except Exception as e:
            logger.error("Error seeding baselines: %s", e, exc_info=True)

    # ── Event analysis ────────────────────────────────────────────────────

    async def analyze(self, evento_id: str, evento_dict: dict):
        """Analyzes an event asynchronously (fire-and-forget).

        This method is called from Pipeline.process() via create_task.
        Computes z-scores and updates entity risks.

        All errors are caught internally so they do not affect
        the pipeline.

        Args:
            evento_id: UUID of the persisted event.
            evento_dict: Dict with event data for analysis.
        """
        if not settings.analysis_enabled:
            return

        try:
            # 1. Compute anomalies (z-scores)
            zscores = self._compute_event_zscores(evento_dict)

            # 1.5 ML scoring (optional)
            ml_score = None
            if self._ml_engine and self._ml_engine.available:
                ml_score = await self._ml_engine.score(evento_dict)

            # 2. Build and persist analysis_data on the event
            analysis_data = {}
            if zscores:
                analysis_data["zscores"] = zscores
            if ml_score is not None:
                analysis_data["ml_score"] = ml_score

            if analysis_data:
                await self._persist_analysis_data(evento_id, analysis_data)

            # 3. Update entity risk
            await self._update_entity_risk(evento_dict)

        except Exception as e:
            logger.error(
                "Error analyzing event %s: %s",
                evento_id,
                e,
                exc_info=True,
            )

    def _compute_event_zscores(self, evento_dict: dict) -> dict[str, float]:
        """Computes z-scores for the event's numeric fields.

        Only computes for fields that have an available baseline
        and valid numeric values.

        Args:
            evento_dict: Dict with event data.

        Returns:
            Dict with {field: zscore} for anomalous fields.
            Empty if there are no baselines or numeric fields.
        """
        if not self._baselines:
            return {}

        zscores = {}
        for campo, valor in _extract_numeric_fields(evento_dict).items():
            baseline = self._baselines.get(campo)
            if baseline and baseline["std"] > 0:
                z = _compute_zscore(valor, baseline["mean"], baseline["std"])
                if z is not None and abs(z) >= 2.0:  # anomaly threshold
                    zscores[campo] = round(z, 4)

        return zscores

    async def _persist_analysis_data(
        self, evento_id: str, analysis_data: dict[str, object]
    ):
        """Persists analysis_data into event.analysis_data (JSONB).

        Args:
            evento_id: UUID of the event.
            analysis_data: Dict with analysis data (zscores, ml_score, etc.).
        """
        try:
            async with self._session_factory() as session:
                from app.models.event import NormalizedEvent

                result = await session.execute(
                    select(NormalizedEvent).where(NormalizedEvent.id == evento_id)
                )
                evento = result.scalar_one_or_none()
                if evento:
                    evento.analysis_data = analysis_data
                    session.add(evento)
                    await session.commit()
                    logger.debug(
                        "Analysis data persisted for event %s: %s",
                        evento_id,
                        analysis_data,
                    )
        except Exception as e:
            logger.error(
                "Error persisting analysis_data for %s: %s",
                evento_id,
                e,
            )

    async def _update_entity_risk(self, evento_dict: dict):
        """Updates the entity risk based on the event.

        Determines the entity_key from source_ip, user_name, or source.
        Applies an increment based on the event severity.

        Args:
            evento_dict: Dict with event data.
        """
        if not self._risk_store:
            return

        entity_key = (
            evento_dict.get("source_ip")
            or evento_dict.get("user_name")
            or evento_dict.get("source")
        )

        if not entity_key:
            return

        # Increment based on severity
        severidad = evento_dict.get("severity", "info")
        incrementos = {
            "critical": 0.15,
            "high": 0.10,
            "medium": 0.05,
            "low": 0.02,
            "info": 0.01,
        }
        incremento = incrementos.get(severidad, 0.01)

        await self._risk_store.update_risk(entity_key, incremento)

    # ── Query properties ──────────────────────────────────────────────────

    async def get_anomalies(
        self,
        limit: int = 50,
        offset: int = 0,
        min_zscore: float = 2.0,
    ) -> tuple[list[dict], int]:
        """Queries events with analysis_data (detected anomalies).

        Args:
            limit: Maximum number of results.
            offset: Offset for pagination.
            min_zscore: Minimum z-score to filter.

        Returns:
            Tuple (list of anomalous events, total).
        """
        try:
            async with self._session_factory() as session:
                # Use raw SQL because JSONB has no full support
                # via SQLAlchemy JSON type in all versions
                query = text(
                    """SELECT id, source, collector_type, event_type, severity,
                              description, source_ip, destination_ip, source_port,
                              destination_port, user_name, event_timestamp,
                              analysis_data
                       FROM events
                       WHERE analysis_data IS NOT NULL
                       ORDER BY event_timestamp DESC
                       LIMIT :lim OFFSET :off"""
                )

                result = await session.execute(query, {"lim": limit, "off": offset})
                rows = result.fetchall()

                count_result = await session.execute(
                    text("SELECT COUNT(*) FROM events WHERE analysis_data IS NOT NULL")
                )
                total = count_result.scalar() or 0

                anomalias = []
                for row in rows:
                    anomalias.append(
                        {
                            "id": str(row[0]),
                            "source": row[1],
                            "collector_type": row[2],
                            "event_type": row[3],
                            "severity": row[4],
                            "description": (row[5] or "")[:200],
                            "source_ip": row[6],
                            "destination_ip": row[7],
                            "source_port": row[8],
                            "destination_port": row[9],
                            "user_name": row[10],
                            "event_timestamp": row[11].isoformat() if row[11] else None,
                            "analysis_data": row[12],
                        }
                    )

                return anomalias, total

        except Exception as e:
            logger.error("Error querying anomalies: %s", e, exc_info=True)
            return [], 0

    async def get_risks(
        self, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict], int]:
        """Queries risk scores per entity.

        Args:
            limit: Maximum number of results.
            offset: Offset for pagination.

        Returns:
            Tuple (list of risks, total).
        """
        if not self._risk_store:
            return [], 0

        all_risks = self._risk_store.get_all_risks()
        total = len(all_risks)
        paginated = all_risks[offset : offset + limit]
        return paginated, total

    # ── Background grouping task ─────────────────────────────────────────

    async def _start_grouping_task(self):
        """Start background alert grouping loop."""
        self._grouping_task = asyncio.create_task(self._grouping_loop())

    async def _grouping_loop(self):
        """Background loop that groups open alerts every 60 seconds."""
        while True:
            try:
                await asyncio.sleep(60)
                async with self._session_factory() as session:
                    from app.services.alert_service import AlertService

                    alert_service = AlertService(session)
                    updated = await alert_service.agrupar_alertas_abiertas()
                    if updated > 0:
                        logger.info("Grouping task: %d alerts updated", updated)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in grouping task: %s", e, exc_info=True)
                await asyncio.sleep(60)

    async def shutdown(self):
        """Cancel background tasks gracefully."""
        if hasattr(self, "_grouping_task") and self._grouping_task:
            self._grouping_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._grouping_task
        if self._ml_engine:
            await self._ml_engine.shutdown()
