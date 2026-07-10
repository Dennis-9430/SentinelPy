"""Motor de ML para detección de anomalías con IsolationForest.

Opcional — si numpy/sklearn no están instalados, el motor se desactiva
gracefully con un warning en logs. Inferencia via run_in_executor
para no bloquear el event loop.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

# Check if ML deps are available
try:
    import numpy as np
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    np = None  # type: ignore
    IsolationForest = None  # type: ignore
    StandardScaler = None  # type: ignore


class MLEngine:
    """IsolationForest wrapper for anomaly scoring.

    - Trains on boot from recent events (if enough data)
    - Re-trains periodically (every N events)
    - Inference via run_in_executor (non-blocking)
    - Graceful fallback if deps missing
    """

    def __init__(
        self,
        session_factory,
        retrain_interval: int = 100,
    ):
        self._session_factory = session_factory
        self._model: Any = None
        self._scaler: Any = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._event_count = 0
        self._retrain_interval = retrain_interval
        self._trained = False

        if not ML_AVAILABLE:
            logger.warning(
                "numpy/scikit-learn not installed — ML engine disabled. "
                "Install with: pip install numpy scikit-learn"
            )

    @property
    def available(self) -> bool:
        return ML_AVAILABLE and self._trained

    async def init_async(self):
        """Train initial model from recent events."""
        if not ML_AVAILABLE:
            return
        try:
            await self._train_model()
        except Exception as e:
            logger.warning("ML model training failed: %s", e)

    async def score(self, evento_dict: dict) -> float | None:
        """Compute anomaly score for an event.

        Returns a score in [-1, 1] range (lower = more anomalous).
        Returns None if ML is unavailable or model not trained.
        """
        if not ML_AVAILABLE or self._model is None:
            return None

        try:
            features = self._extract_features(evento_dict)
            if features is None:
                return None

            loop = asyncio.get_event_loop()
            score = await loop.run_in_executor(
                self._executor,
                self._predict,
                features,
            )

            # Retrain periodically
            self._event_count += 1
            if self._event_count % self._retrain_interval == 0:
                asyncio.create_task(self._train_model())

            return float(score)

        except Exception as e:
            logger.error("ML scoring error: %s", e, exc_info=True)
            return None

    def _extract_features(self, evento_dict: dict) -> list[float] | None:
        """Extract numeric feature vector from event dict.

        Features: source_port, destination_port, event_count, duration,
                  bytes_sent, bytes_received (same as z-score fields).
        Returns None if no numeric features found.
        """
        if not ML_AVAILABLE:
            return None

        from app.services.analysis_service import CAMPOS_NUMERICOS

        features = []
        for campo in CAMPOS_NUMERICOS:
            val = evento_dict.get(campo)
            if val is not None:
                try:
                    features.append(float(val))
                except (ValueError, TypeError):
                    features.append(0.0)
            else:
                features.append(0.0)

        # At least 1 non-zero feature
        if all(f == 0.0 for f in features):
            return None

        return features

    def _predict(self, features: list[float]) -> float:
        """Synchronous prediction (runs in thread pool)."""
        if not ML_AVAILABLE or self._model is None:
            return 0.0
        X = np.array([features])
        X_scaled = self._scaler.transform(X)
        # decision_function returns anomaly score (lower = more anomalous)
        score = self._model.decision_function(X_scaled)[0]
        return float(score)

    async def _train_model(self):
        """Train IsolationForest from recent events."""
        if not ML_AVAILABLE:
            return

        try:
            async with self._session_factory() as session:
                from app.models.event import NormalizedEvent
                from sqlalchemy import select
                from datetime import UTC, datetime, timedelta

                # Get last 1000 events for training
                desde = datetime.now(UTC) - timedelta(hours=24)
                result = await session.execute(
                    select(NormalizedEvent)
                    .where(NormalizedEvent.event_timestamp >= desde)
                    .order_by(NormalizedEvent.event_timestamp.desc())
                    .limit(1000)
                )
                eventos = result.scalars().all()

                if len(eventos) < 50:
                    logger.info(
                        "Not enough events for ML training (%d/50 min)",
                        len(eventos),
                    )
                    return

                # Build feature matrix
                from app.services.analysis_service import CAMPOS_NUMERICOS
                import numpy as local_np

                X = []
                for ev in eventos:
                    row = []
                    for campo in CAMPOS_NUMERICOS:
                        val = getattr(ev, campo, None)
                        try:
                            row.append(float(val) if val is not None else 0.0)
                        except (ValueError, TypeError):
                            row.append(0.0)
                    X.append(row)

                X_array = local_np.array(X)

                # Train
                self._scaler = StandardScaler()
                X_scaled = self._scaler.fit_transform(X_array)

                self._model = IsolationForest(
                    contamination=0.1,
                    random_state=42,
                    n_estimators=100,
                )
                self._model.fit(X_scaled)
                self._trained = True

                logger.info(
                    "ML model trained: %d events, %d features",
                    len(X),
                    X_array.shape[1],
                )

        except Exception as e:
            logger.error("ML training error: %s", e, exc_info=True)

    async def shutdown(self):
        """Shutdown thread pool executor."""
        self._executor.shutdown(wait=False)
