"""Pipeline de procesamiento: conecta colectores, parsers y base de datos.

El pipeline es el "middleware" interno de SentinelPy. Recibe logs crudos
de cualquier colector, los parsea según su formato, y los persiste.
También los envía al motor de correlación (cuando esté implementado).
"""

import logging
from datetime import datetime, timezone
from app.services.parser import SyslogParser, JSONParser
from app.database import async_session

logger = logging.getLogger(__name__)


class Pipeline:
    """Pipeline que procesa logs desde los colectores hasta la base de datos.

    Flujo:
        Colector → Pipeline.process(raw) → Parser.detect() → Parser.parse() → DB

    Detecta automáticamente si el log es JSON o syslog según el primer carácter.
    """

    def __init__(self):
        """Inicializa los parsers disponibles."""
        self.syslog_parser = SyslogParser()
        self.json_parser = JSONParser()

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
            logger.warning("No se pudo parsear el log (formato desconocido): %s", raw[:100])
            return None

        # Si tenemos información del origen, actualizar el source
        if origen and not datos_parseados.get("source"):
            datos_parseados["source"] = f"{origen[0]}:{origen[1]}"

        # Guardar en base de datos
        evento = await self._guardar_evento(datos_parseados)

        if evento:
            logger.info(
                "Evento procesado: %s | %s | %s",
                evento.event_type,
                evento.severity,
                evento.source,
            )

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
            async with async_session() as session:
                evento = NormalizedEvent(**datos)
                session.add(evento)
                await session.commit()
                await session.refresh(evento)
                return evento
        except Exception as e:
            logger.error("Error guardando evento en DB: %s", e, exc_info=True)
            return None
