"""Pipeline de procesamiento: conecta colectores, parsers y base de datos.

El pipeline es el "middleware" interno de SentinelPy. Recibe logs crudos
de cualquier colector, los parsea según su formato, y los persiste.
También los envía al motor de correlación y al servicio de análisis.
"""

import asyncio
import logging

from app.config import settings
from app.database import async_session as _default_session
from app.services.parser import JSONParser, SyslogParser

logger = logging.getLogger(__name__)


class Pipeline:
    """Pipeline que procesa logs desde los colectores hasta la base de datos.

    Flujo:
        Colector → Pipeline.process(raw) → Parser.detect() → Parser.parse() → DB
        → (async) AnalysisService.analyze() → Engine.evaluate()

    Detecta automáticamente si el log es JSON o syslog según el primer carácter.
    """

    def __init__(self, engine=None, session_factory=None, analysis_service=None, ti_service=None):
        """Inicializa los parsers disponibles.

        Argumentos:
            engine: Instancia opcional de CorrelationEngine para evaluación.
            session_factory: async_sessionmaker para persistencia.
                Por defecto usa app.database.async_session.
            analysis_service: Instancia opcional de AnalysisService para análisis.
            ti_service: Instancia opcional de ThreatIntelService para enriquecimiento.
        """
        self.syslog_parser = SyslogParser()
        self.json_parser = JSONParser()
        self.engine = engine
        self.analysis_service = analysis_service
        self.ti_service = ti_service
        self._session_factory = session_factory or _default_session

    async def process(self, raw: str, origen: tuple | None = None) -> dict | None:
        """Procesa un log crudo: detecta formato, parsea y guarda.

        Este método se llama desde los colectores cuando reciben un mensaje.
        Detecta automáticamente el formato (JSON vs syslog), parsea,
        y guarda el resultado en la base de datos.

        Argumentos:
            raw: Texto crudo del log.
            origen: Tupla (host, port) del remitente (opcional).

        Retorna:
            Dict con el evento creado, o None si falló.
        """
        if not raw or not raw.strip():
            return None

        # Detectar formato y parsear
        datos_parseados = self._detectar_y_parsear(raw)

        if not datos_parseados:
            logger.warning(
                "No se pudo parsear el log (formato desconocido): %s", raw[:100]
            )
            return None

        # Si tenemos información del origen, actualizar el source
        if origen and not datos_parseados.get("source"):
            datos_parseados["source"] = f"{origen[0]}:{origen[1]}"

        # Asegurar que source tenga un valor (columna NOT NULL en DB)
        if not datos_parseados.get("source"):
            datos_parseados["source"] = "unknown"

        # Guardar en base de datos
        evento = await self._guardar_evento(datos_parseados)

        if evento:
            logger.info(
                "Evento procesado: %s | %s | %s",
                evento.event_type,
                evento.severity,
                evento.source,
            )

            # ── Análisis estadístico (fire-and-forget) ──────────────────
            if self.analysis_service:
                evento_dict = self._evento_to_dict(evento)
                asyncio.create_task(
                    self.analysis_service.analyze(str(evento.id), evento_dict)
                )

            # ── Threat Intelligence enrichment (fire-and-forget) ────────
            if self.ti_service and settings.ti_enrichment_enabled:
                evento_dict = self._evento_to_dict(evento)
                asyncio.create_task(self._enrich_ti(evento_dict))

            # ── Evaluar contra el motor de correlación ──────────────────
            if self.engine:
                evento_dict = self._evento_to_dict(evento)
                alertas = await self.engine.evaluate(evento_dict)
                if alertas:
                    logger.info(
                        "Evento %s generó %d alerta(s)",
                        evento.event_type,
                        len(alertas),
                    )

        return evento

    @staticmethod
    def _evento_to_dict(evento) -> dict:
        """Convierte un ORM event a dict para pasarlo al engine.

        Argumentos:
            evento: Instancia de NormalizedEvent.

        Retorna:
            Dict con campos serializados para engine.evaluate().
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
        """Procesa un dict de evento ya normalizado a través del pipeline completo.

        Similar a process() pero recibe un dict ya parseado en lugar de raw text.
        Guarda en DB y evalúa contra el motor de correlación.

        Útil para endpoints REST donde el evento ya viene normalizado (EventCreate).

        Argumentos:
            datos: Dict con campos normalizados del evento.
            collector_type: Si se provee, sobreescribe collector_type en los datos.

        Retorna:
            Instancia de NormalizedEvent, o None si falló la persistencia.
        """
        if collector_type:
            datos["collector_type"] = collector_type

        if not datos.get("source"):
            datos["source"] = "unknown"

        # Guardar en base de datos
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
                        "Evento %s generó %d alerta(s)",
                        evento.event_type,
                        len(alertas),
                    )
            except Exception as e:
                logger.error("Error en engine.evaluate: %s", e, exc_info=True)

        return evento

    def _detectar_y_parsear(self, raw: str) -> dict | None:
        """Detecta el formato del log y lo parsea con el parser adecuado.

        Estrategia:
            - Si empieza con '{' → probar JSON
            - Si no → probar syslog RFC 3164

        Argumentos:
            raw: Texto crudo del log.

        Retorna:
            Dict con campos normalizados, o None.
        """
        stripped = raw.strip()

        # Detectar JSON (empieza con llave)
        if stripped.startswith("{"):
            resultado = self.json_parser.parse(stripped)
            if resultado:
                return resultado

        # Detectar syslog (empieza con <)
        if stripped.startswith("<"):
            resultado = self.syslog_parser.parse(stripped)
            if resultado:
                return resultado

        # Último recurso: intentar JSON aunque no empiece con {
        resultado = self.json_parser.parse(stripped)
        if resultado:
            return resultado

        return None

    async def _guardar_evento(self, datos: dict) -> object | None:
        """Persiste un evento normalizado en la base de datos.

        Crea una sesión propia porque este método se llama desde
        contextos fuera de las dependencias de FastAPI (ej: UDP handler).

        Argumentos:
            datos: Dict con campos normalizados del evento.

        Retorna:
            Instancia de NormalizedEvent, o None si falló.
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
            logger.error("Error guardando evento en DB: %s", e, exc_info=True)
            return None

    async def _enrich_ti(self, evento_dict: dict) -> None:
        """Enriquece un evento con datos de Threat Intelligence (fire-and-forget).

        Consulta los providers de TI registrados y almacena los resultados
        en analysis_data["ti"] del evento.

        Argumentos:
            evento_dict: Dict con datos del evento normalizado.
        """
        try:
            ti_data = await self.ti_service.enrich(evento_dict)
            if ti_data:
                event_id = evento_dict.get("id")
                if event_id:
                    from app.models.event import NormalizedEvent

                    async with self._session_factory() as session:
                        event = await session.get(NormalizedEvent, event_id)
                        if event:
                            analysis = event.analysis_data or {}
                            analysis["ti"] = ti_data
                            event.analysis_data = analysis
                            await session.commit()
        except Exception:
            pass  # Never propagate TI errors
