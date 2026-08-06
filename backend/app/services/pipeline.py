"""Processing pipeline: connects collectors, parsers and the database.

The pipeline is SentinelPy's internal "middleware". It receives raw logs
from any collector, parses them according to their format, and persists them.
It also sends them to the correlation engine and the analysis service.
"""

import asyncio
import logging

from app.database import async_session as _default_session
from app.services.parser import JSONParser, SyslogParser

logger = logging.getLogger(__name__)


class Pipeline:
    """Pipeline that processes logs from collectors to the database.

    Flow:
        Collector → Pipeline.process(raw) → Parser.detect() → Parser.parse() → DB
        → (async) AnalysisService.analyze() → Engine.evaluate()

    Automatically detects whether the log is JSON or syslog based on the first character.
    """

    def __init__(self, engine=None, session_factory=None, analysis_service=None):
        """Initialize the available parsers.

        Args:
            engine: Optional CorrelationEngine instance for evaluation.
            session_factory: async_sessionmaker for persistence.
                Defaults to app.database.async_session.
            analysis_service: Optional AnalysisService instance for analysis.
        """
        self.syslog_parser = SyslogParser()
        self.json_parser = JSONParser()
        self.engine = engine
        self.analysis_service = analysis_service
        self._session_factory = session_factory or _default_session

    async def process(self, raw: str, origen: tuple | None = None) -> dict | None:
        """Process a raw log: detect format, parse and save.

        This method is called from the collectors when they receive a message.
        It automatically detects the format (JSON vs syslog), parses,
        and saves the result to the database.

        Args:
            raw: Raw log text.
            origen: (host, port) tuple of the sender (optional).

        Returns:
            Dict with the created event, or None if it failed.
        """
        if not raw or not raw.strip():
            return None

        # Detect format and parse
        datos_parseados = self._detectar_y_parsear(raw)

        if not datos_parseados:
            logger.warning(
                "Could not parse the log (unknown format): %s", raw[:100]
            )
            return None

        # If we have origin information, update the source
        if origen and not datos_parseados.get("source"):
            datos_parseados["source"] = f"{origen[0]}:{origen[1]}"

        # Ensure source has a value (NOT NULL column in DB)
        if not datos_parseados.get("source"):
            datos_parseados["source"] = "unknown"

        # Save to database
        evento = await self._guardar_evento(datos_parseados)

        if evento:
            logger.info(
                "Event processed: %s | %s | %s",
                evento.event_type,
                evento.severity,
                evento.source,
            )

            # ── Statistical analysis (fire-and-forget) ──────────────────
            if self.analysis_service:
                evento_dict = self._evento_to_dict(evento)
                asyncio.create_task(
                    self.analysis_service.analyze(str(evento.id), evento_dict)
                )

            # ── Evaluate against the correlation engine ──────────────────
            if self.engine:
                evento_dict = self._evento_to_dict(evento)
                alertas = await self.engine.evaluate(evento_dict)
                if alertas:
                    logger.info(
                        "Event %s generated %d alert(s)",
                        evento.event_type,
                        len(alertas),
                    )

        return evento

    @staticmethod
    def _evento_to_dict(evento) -> dict:
        """Convert an ORM event to a dict to pass to the engine.

        Args:
            evento: NormalizedEvent instance.

        Returns:
            Dict with serialized fields for engine.evaluate().
        """
        return {
            "id": str(evento.id),
            "source": evento.source,
            "collector_type": evento.collector_type,
            "event_timestamp": evento.event_timestamp,
            "event_type": evento.event_type,
            "severity": evento.severity,
            "description": evento.description,
            "source_ip": evento.source_ip,
            "destination_ip": evento.destination_ip,
            "source_port": evento.source_port,
            "destination_port": evento.destination_port,
            "protocol": evento.protocol,
            "user_name": evento.user_name,
            "process_name": evento.process_name,
            "file_path": evento.file_path,
        }

    async def process_from_dict(
        self, datos: dict, collector_type: str | None = None
    ) -> object | None:
        """Process an already normalized event dict through the full pipeline.

        Similar to process() but receives an already parsed dict instead of raw text.
        Saves to DB and evaluates against the correlation engine.

        Useful for REST endpoints where the event already comes normalized (EventCreate).

        Args:
            datos: Dict with normalized event fields.
            collector_type: If provided, overrides collector_type in the data.

        Returns:
            NormalizedEvent instance, or None if persistence failed.
        """
        if collector_type:
            datos["collector_type"] = collector_type

        if not datos.get("source"):
            datos["source"] = "unknown"

        # Save to database
        evento = await self._guardar_evento(datos)

        if evento and self.analysis_service:
            evento_dict_analysis = self._evento_to_dict(evento)
            asyncio.create_task(
                self.analysis_service.analyze(str(evento.id), evento_dict_analysis)
            )

        if evento and self.engine:
            evento_dict = self._evento_to_dict(evento)

            try:
                alertas = await self.engine.evaluate(evento_dict)
                if alertas:
                    logger.info(
                        "Event %s generated %d alert(s)",
                        evento.event_type,
                        len(alertas),
                    )
            except Exception as e:
                logger.error("Error in engine.evaluate: %s", e, exc_info=True)

        return evento

    def _detectar_y_parsear(self, raw: str) -> dict | None:
        """Detect the log format and parse it with the appropriate parser.

        Strategy:
            - If it starts with '{' → try JSON
            - If not → try syslog RFC 3164

        Args:
            raw: Raw log text.

        Returns:
            Dict with normalized fields, or None.
        """
        stripped = raw.strip()

        # Detect JSON (starts with brace)
        if stripped.startswith("{"):
            resultado = self.json_parser.parse(stripped)
            if resultado:
                return resultado

        # Detect syslog (starts with <)
        if stripped.startswith("<"):
            resultado = self.syslog_parser.parse(stripped)
            if resultado:
                return resultado

        # Last resort: try JSON even if it does not start with {
        resultado = self.json_parser.parse(stripped)
        if resultado:
            return resultado

        return None

    async def _guardar_evento(self, datos: dict) -> object | None:
        """Persist a normalized event to the database.

        Creates its own session because this method is called from
        contexts outside FastAPI dependencies (e.g. UDP handler).

        Args:
            datos: Dict with normalized event fields.

        Returns:
            NormalizedEvent instance, or None if it failed.
        """
        from app.models.event import NormalizedEvent

        try:
            async with self._session_factory() as session:
                evento = NormalizedEvent(**datos)
                session.add(evento)
                await session.commit()
                await session.refresh(evento)
                return evento
        except Exception as e:
            logger.error("Error saving event to DB: %s", e, exc_info=True)
            return None
