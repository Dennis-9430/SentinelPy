"""Servicio de análisis estadístico y scoring de riesgo.

Implementa:
  - Z-score baselines para detección de anomalías
  - Entity risk scoring con decaimiento exponencial
  - ML inference (IsolationForest) cuando está disponible (Slice 3)

Todas las operaciones de análisis son no-bloqueantes (fire-and-forget).
"""

import asyncio
import logging
import math
import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

# ── Constantes de análisis ──────────────────────────────────────────────────

CAMPOS_NUMERICOS = {
    "source_port",
    "destination_port",
    "event_count",
    "duration",
    "bytes_sent",
    "bytes_received",
}

# ═══════════════════════════════════════════════════════════════════════════
# Funciones puras (testeables sin DB ni mocks)
# ═══════════════════════════════════════════════════════════════════════════


def _is_numeric(valor: Any) -> bool:
    """Verifica si un valor es numérico (int o float, no bool).

    Argumentos:
        valor: Valor a verificar.

    Retorna:
        True si es int o float (no bool).
    """
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _compute_baseline_stats(valores: list[float]) -> tuple[float, float]:
    """Calcula media y desvío estándar poblacional de una lista de valores.

    Usa ddof=1 (sample standard deviation) para mejor estimación.

    Argumentos:
        valores: Lista de floats.

    Retorna:
        Tupla (mean, std). Si la lista está vacía, retorna (0.0, 0.0).
    """
    if not valores:
        return 0.0, 0.0
    if len(valores) < 2:
        return float(valores[0]), 0.0
    mean = statistics.mean(valores)
    std = statistics.stdev(valores)
    return mean, std


def _extract_numeric_fields(evento: dict) -> dict[str, float]:
    """Extrae campos numéricos relevantes de un evento.

    Filtra solo los campos definidos en CAMPOS_NUMERICOS que tengan
    valores numéricos no-None.

    Argumentos:
        evento: Dict con datos del evento.

    Retorna:
        Dict con {campo: valor_numérico}.
    """
    result = {}
    for campo in CAMPOS_NUMERICOS:
        valor = evento.get(campo)
        if _is_numeric(valor):
            result[campo] = float(valor)
    return result


def _compute_zscore(value: float, mean: float, std: float) -> float | None:
    """Computa el z-score de un valor contra una baseline.

    Fórmula: z = (value - mean) / std

    Argumentos:
        value: Valor a evaluar.
        mean: Media de la baseline.
        std: Desvío estándar de la baseline.

    Retorna:
        Z-score como float, o None si std <= 0 (no hay variación).
    """
    if std <= 0:
        return None
    return (value - mean) / std


def _increment_risk(
    current: float, increment: float, max_risk: float
) -> float:
    """Incrementa un score de riesgo con cap en max_risk.

    Argumentos:
        current: Score actual (0.0 a max_risk).
        increment: Incremento a aplicar.
        max_risk: Valor máximo permitido.

    Retorna:
        Score incrementado, capedo en max_risk.
    """
    nuevo = current + increment
    return min(nuevo, max_risk)


def _decay_risk(
    score: float, decay_rate: float, elapsed_seconds: float
) -> float:
    """Aplica decaimiento exponencial a un score de riesgo.

    Fórmula: score * exp(-decay_rate * elapsed_hours)

    Donde elapsed_hours = elapsed_seconds / 3600.

    Argumentos:
        score: Score actual a decaer.
        decay_rate: Tasa de decaimiento (ej: 0.5 = reducir a la mitad por hora).
        elapsed_seconds: Segundos transcurridos desde último update.

    Retorna:
        Score decaído.
    """
    if score <= 0 or decay_rate <= 0 or elapsed_seconds <= 0:
        return score
    elapsed_hours = elapsed_seconds / 3600.0
    return score * math.exp(-decay_rate * elapsed_hours)


# ═══════════════════════════════════════════════════════════════════════════
# Entity Risk
# ═══════════════════════════════════════════════════════════════════════════


class EntityRiskStore:
    """Almacén de riesgos por entidad con write-through a DB.

    Mantiene un dict en memoria para lecturas rápidas y persiste
    cada actualización a la tabla entity_risks.

    Los riesgos se identifican por entity_key (ej: IP, username).
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self._risks: dict[str, float] = {}
        self._timestamps: dict[str, datetime] = {}

    async def load_from_db(self):
        """Carga todos los riesgos desde la DB al iniciar."""
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
                    logger.info(
                        "Riesgos cargados desde DB: %d entidades", len(rows)
                    )
        except Exception as e:
            logger.warning("No se pudieron cargar riesgos desde DB: %s", e)

    async def get_or_create(self, entity_key: str) -> float:
        """Obtiene el riesgo actual de una entidad.

        Si no existe, lo crea con score 0.0 y lo persiste.

        Argumentos:
            entity_key: Clave única de la entidad.

        Retorna:
            Score de riesgo actual (float).
        """
        if entity_key not in self._risks:
            self._risks[entity_key] = 0.0
            self._timestamps[entity_key] = datetime.now(UTC)
            await self._persist(entity_key, 0.0)
        return self._risks[entity_key]

    async def update_risk(
        self, entity_key: str, increment: float
    ) -> float:
        """Incrementa el riesgo de una entidad con write-through.

        Aplica decaimiento primero si pasó tiempo desde último update,
        luego aplica el incremento con cap en max_risk.

        Argumentos:
            entity_key: Clave única de la entidad.
            increment: Cuánto incrementar.

        Retorna:
            Nuevo score después de incremento.
        """
        ahora = datetime.now(UTC)
        current = self._risks.get(entity_key, 0.0)

        # Aplicar decaimiento si pasó tiempo
        if entity_key in self._timestamps:
            elapsed = (ahora - self._timestamps[entity_key]).total_seconds()
            if elapsed > 0:
                current = _decay_risk(
                    current, settings.analysis_decay_rate, elapsed
                )

        nuevo = _increment_risk(
            current, increment, settings.analysis_max_risk
        )

        self._risks[entity_key] = nuevo
        self._timestamps[entity_key] = ahora
        await self._persist(entity_key, nuevo)
        return nuevo

    async def _persist(self, entity_key: str, score: float):
        """Persiste un score de riesgo en la tabla entity_risks.

        Usa INSERT ... ON CONFLICT DO UPDATE (upsert).
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
            logger.error(
                "Error persistiendo riesgo para %s: %s", entity_key, e
            )

    def get_all_risks(self) -> list[dict]:
        """Retorna todos los riesgos en memoria para consulta.

        Retorna:
            Lista de dicts con entity_key, risk_score, updated_at.
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
    """Servicio de análisis estadístico de eventos.

    Mantiene baselines en memoria (media/std por campo) seedeadas desde DB,
    calcula z-scores por evento, y actualiza riesgos por entidad.

    Flujo:
        1. Al iniciar, seed baselines desde DB (query últimos N eventos)
        2. Por cada evento que llega, compute z-scores + update risk
        3. Resultados se persisten en event.analysis_data y entity_risks
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self._baselines: dict[str, dict] = {}
        # entity_risk_store se inicializa en init_async
        self._risk_store: EntityRiskStore | None = None

    async def init_async(self):
        """Inicializa el servicio: crea entity_risks table, carga riesgos y baselines.

        Debe llamarse después de crear la instancia, en el lifespan de la app.
        """
        # Asegurar que la tabla entity_risks existe
        await self._ensure_entity_risks_table()

        # Inicializar risk store
        self._risk_store = EntityRiskStore(self._session_factory)
        await self._risk_store.load_from_db()

        # Seed baselines
        await self.seed_baselines()

        # Iniciar background grouping task
        await self._start_grouping_task()

        logger.info("AnalysisService inicializado")

    async def _ensure_entity_risks_table(self):
        """Crea la tabla entity_risks si no existe."""
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
            logger.warning("Error creando tabla entity_risks: %s", e)

    # ── Baseline management ───────────────────────────────────────────────

    async def seed_baselines(self):
        """Seeder de baselines desde la base de datos.

        Consulta los últimos N eventos (ANALYSIS_BASELINE_WINDOW_MINUTES)
        y calcula media/std para cada campo numérico.

        Si no hay datos suficientes, los baselines quedan vacíos
        y se computarán a medida que lleguen eventos.
        """
        try:
            async with self._session_factory() as session:
                from app.models.event import NormalizedEvent

                # Calcular timestamp del window
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
                        "No hay eventos en la ventana de baseline (%d min)",
                        settings.analysis_baseline_window_minutes,
                    )
                    return

                # Agrupar valores por campo
                valores_por_campo: dict[str, list[float]] = {}
                for ev in eventos:
                    for campo in CAMPOS_NUMERICOS:
                        valor = getattr(ev, campo, None)
                        if _is_numeric(valor):
                            valores_por_campo.setdefault(campo, []).append(
                                float(valor)
                            )

                # Calcular estadísticas por campo
                for campo, valores in valores_por_campo.items():
                    if len(valores) >= 10:  # mínimo 10 valores para baseline
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
                    "Baselines seedeados: %d campos con datos suficientes",
                    len(self._baselines),
                )

        except Exception as e:
            logger.error("Error seedeando baselines: %s", e, exc_info=True)

    # ── Análisis de evento ─────────────────────────────────────────────────

    async def analyze(self, evento_id: str, evento_dict: dict):
        """Analiza un evento de forma asíncrona (fire-and-forget).

        Este método se llama desde Pipeline.process() via create_task.
        Calcula z-scores y actualiza riesgos de entidad.

        Todos los errores se capturan internamente para no afectar
        al pipeline.

        Argumentos:
            evento_id: UUID del evento persistido.
            evento_dict: Dict con datos del evento para análisis.
        """
        if not settings.analysis_enabled:
            return

        try:
            # 1. Calcular anomalías (z-scores)
            zscores = self._compute_event_zscores(evento_dict)

            # 2. Persistir analysis_data en el evento
            if zscores:
                await self._persist_analysis_data(evento_id, zscores)

            # 3. Actualizar riesgo de entidad
            await self._update_entity_risk(evento_dict)

        except Exception as e:
            logger.error(
                "Error analizando evento %s: %s",
                evento_id,
                e,
                exc_info=True,
            )

    def _compute_event_zscores(self, evento_dict: dict) -> dict[str, float]:
        """Computa z-scores para los campos numéricos del evento.

        Solo computa para campos que tengan baseline disponible
        y valores numéricos válidos.

        Argumentos:
            evento_dict: Dict con datos del evento.

        Retorna:
            Dict con {campo: zscore} para campos con anomalías.
            Vacío si no hay baselines o campos numéricos.
        """
        if not self._baselines:
            return {}

        zscores = {}
        for campo, valor in _extract_numeric_fields(evento_dict).items():
            baseline = self._baselines.get(campo)
            if baseline and baseline["std"] > 0:
                z = _compute_zscore(valor, baseline["mean"], baseline["std"])
                if z is not None and abs(z) >= 2.0:  # umbral de anomalía
                    zscores[campo] = round(z, 4)

        return zscores

    async def _persist_analysis_data(
        self, evento_id: str, zscores: dict[str, float]
    ):
        """Persiste los z-scores en event.analysis_data (JSONB).

        Argumentos:
            evento_id: UUID del evento.
            zscores: Dict con {campo: zscore}.
        """
        try:
            async with self._session_factory() as session:
                from app.models.event import NormalizedEvent

                result = await session.execute(
                    select(NormalizedEvent).where(
                        NormalizedEvent.id == evento_id
                    )
                )
                evento = result.scalar_one_or_none()
                if evento:
                    evento.analysis_data = {"zscores": zscores}
                    session.add(evento)
                    await session.commit()
                    logger.debug(
                        "Analysis data persistido para evento %s: %s",
                        evento_id,
                        zscores,
                    )
        except Exception as e:
            logger.error(
                "Error persistiendo analysis_data para %s: %s",
                evento_id,
                e,
            )

    async def _update_entity_risk(self, evento_dict: dict):
        """Actualiza el riesgo de la entidad basado en el evento.

        Determina la entity_key según source_ip, user_name, o source.
        Aplica un incremento según la severidad del evento.

        Argumentos:
            evento_dict: Dict con datos del evento.
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

        # Incremento según severidad
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

    # ── Propiedades de consulta ───────────────────────────────────────────

    async def get_anomalies(
        self,
        limit: int = 50,
        offset: int = 0,
        min_zscore: float = 2.0,
    ) -> tuple[list[dict], int]:
        """Consulta eventos con analysis_data (anomalías detectadas).

        Argumentos:
            limit: Máximo de resultados.
            offset: Offset para paginación.
            min_zscore: Z-score mínimo para filtrar.

        Retorna:
            Tupla (lista de eventos anómalos, total).
        """
        try:
            async with self._session_factory() as session:
                # Usar raw SQL porque JSONB no tiene soporte completo
                # via SQLAlchemy JSON type en todas las versiones
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

                result = await session.execute(
                    query, {"lim": limit, "off": offset}
                )
                rows = result.fetchall()

                count_result = await session.execute(
                    text(
                        "SELECT COUNT(*) FROM events WHERE analysis_data IS NOT NULL"
                    )
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
                            "event_timestamp": row[11].isoformat()
                            if row[11]
                            else None,
                            "analysis_data": row[12],
                        }
                    )

                return anomalias, total

        except Exception as e:
            logger.error("Error consultando anomalías: %s", e, exc_info=True)
            return [], 0

    async def get_risks(
        self, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict], int]:
        """Consulta scores de riesgo por entidad.

        Argumentos:
            limit: Máximo de resultados.
            offset: Offset para paginación.

        Retorna:
            Tupla (lista de riesgos, total).
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
            try:
                await self._grouping_task
            except asyncio.CancelledError:
                pass



