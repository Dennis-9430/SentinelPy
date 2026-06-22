"""Parsers de logs: convierten logs crudos al formato normalizado.

Cada parser entiende un formato específico y extrae los campos
comunes para almacenarlos como NormalizedEvent.
"""

import json
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Mapeo de severidad syslog a severidad SentinelPy ─────────────────────
# Los niveles 0-7 de syslog se mapean a nuestro modelo
SYSLOG_SEVERITY_MAP = {
    0: "critical",   # Emergency
    1: "critical",   # Alert
    2: "critical",   # Critical
    3: "high",       # Error
    4: "medium",     # Warning
    5: "low",        # Notice
    6: "info",       # Informational
    7: "info",       # Debug
}

# ── Mapeo de facility syslog ─────────────────────────────────────────────
SYSLOG_FACILITY_MAP = {
    0: "kern",
    1: "user",
    2: "mail",
    3: "daemon",
    4: "auth",
    5: "syslog",
    10: "authpriv",
    16: "local0",
    17: "local1",
    18: "local2",
    19: "local3",
    20: "local4",
    21: "local5",
    22: "local6",
    23: "local7",
}

# ── Regex para RFC 3164 (BSD syslog) ─────────────────────────────────────
# Formato: <PRI>Timestamp Hostname App[PID]: Mensaje
# También soporta sin PID: <PRI>Timestamp Hostname App: Mensaje
RFC3164_PATTERN = re.compile(
    r"^<(\d{1,3})>"                           # 1: Priority (facility*8 + severity)
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"  # 2: Mes
    r"(\d{1,2})\s+"                           # 3: Día
    r"(\d{2}:\d{2}:\d{2})\s+"                 # 4: Hora
    r"(\S+)\s+"                               # 5: Hostname
    r"(\S+?)"                                 # 6: App name
    r"(?:\[(\d+)\])?"                         # 7: PID (opcional)
    r":\s*(.*)"                               # 8: Mensaje
)


class SyslogParser:
    """Parser de syslog: entiende RFC 3164 (BSD).

    RFC 3164: "<PRI>Timestamp Hostname App[PID]: Mensaje"

    Ejemplo:
        <30>Oct  9 22:33:20 myhost sshd[12345]: Failed password for root from 192.168.1.100 port 22 ssh2
    """

    def parse(self, raw: str) -> dict | None:
        """Convierte una línea de syslog a diccionario normalizado.

        Argumentos:
            raw: Línea de texto cruda del syslog.

        Retorna:
            Dict con campos normalizados listo para crear un NormalizedEvent,
            o None si no se pudo parsear.
        """
        if not raw or not raw.strip():
            return None

        # Intentar matchear con RFC 3164
        match = RFC3164_PATTERN.match(raw.strip())
        if not match:
            logger.warning("No se pudo parsear mensaje syslog (formato no reconocido): %s", raw[:100])
            return None

        # Extraer grupos
        priority = int(match.group(1))
        mes = match.group(2)
        dia = match.group(3)
        hora = match.group(4)
        hostname = match.group(5)
        app_name = match.group(6)
        pid = match.group(7)  # Puede ser None
        mensaje = match.group(8)

        # Calcular facility y severity desde el priority
        # Syslog: PRI = facility * 8 + severity
        facility_code = priority // 8
        severity_code = priority % 8

        # Construir timestamp combinando fecha del syslog con año actual
        # RFC 3164 no incluye año, así que usamos el año actual
        año_actual = datetime.now(timezone.utc).year
        timestamp_str = f"{mes} {dia} {hora} {año_actual}"

        try:
            # Parsear fecha estilo syslog: "Oct  9 22:33:20 2026"
            event_timestamp = datetime.strptime(timestamp_str, "%b %d %H:%M:%S %Y")
            event_timestamp = event_timestamp.replace(tzinfo=timezone.utc)
        except ValueError:
            # Si falla, usar timestamp actual
            logger.warning("No se pudo parsear timestamp syslog, usando hora actual")
            event_timestamp = datetime.now(timezone.utc)

        # Determinar tipo de evento según el app name
        event_type = self._detectar_tipo_evento(app_name, mensaje)

        # Extraer IPs del mensaje si están presentes
        source_ip, dest_ip = self._extraer_ips(mensaje)

        return {
            "source": hostname,
            "collector_type": "syslog",
            "event_timestamp": event_timestamp,
            "event_type": event_type,
            "severity": SYSLOG_SEVERITY_MAP.get(severity_code, "info"),
            "description": mensaje,
            "source_ip": source_ip,
            "destination_ip": dest_ip,
            "source_port": None,
            "destination_port": None,
            "protocol": None,
            "user_name": None,
            "process_name": app_name,
            "file_path": None,
            "raw_log": raw,
        }

    def _detectar_tipo_evento(self, app_name: str, mensaje: str) -> str:
        """Detecta el tipo de evento según la aplicación y el mensaje.

        Args:
            app_name: Nombre de la aplicación que generó el log.
            mensaje: Contenido del mensaje.

        Returns:
            String con el tipo de evento normalizado.
        """
        mensaje_lower = mensaje.lower()

        # SSH
        if "ssh" in app_name.lower() or "sshd" in app_name.lower():
            if "failed password" in mensaje_lower:
                return "auth_failure"
            elif "accepted password" in mensaje_lower:
                return "auth_success"
            elif "invalid user" in mensaje_lower:
                return "auth_failure"
            return "auth_attempt"

        # sudo
        if "sudo" in app_name.lower():
            return "privilege_escalation"

        # HTTP
        if app_name.lower() in ("nginx", "apache", "httpd", "http"):
            return "http_request"

        # Si no se pudo determinar, genérico
        return "unknown"

    def _extraer_ips(self, mensaje: str) -> tuple:
        """Extrae direcciones IP del mensaje.

        Args:
            mensaje: Texto del mensaje.

        Returns:
            Tupla (source_ip, destination_ip).
        """
        # Patrón simple para IPv4
        ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", mensaje)

        if len(ips) >= 2:
            return ips[0], ips[1]
        elif len(ips) == 1:
            return ips[0], None
        return None, None


class JSONParser:
    """Parser de logs en formato JSON.

    Útil para logs modernos que ya vienen estructurados (ej: Docker, aplicaciones).
    """

    # Mapeo de nombres de campo del JSON a nuestro modelo normalizado
    FIELD_MAP = {
        "source": ("source", "host", "hostname", "origin"),
        "event_type": ("event_type", "type", "event", "log_type"),
        "severity": ("severity", "level", "log_level", "priority"),
        "description": ("description", "message", "msg", "log", "text"),
        "source_ip": ("source_ip", "src_ip", "source", "src"),
        "destination_ip": ("destination_ip", "dest_ip", "dest", "dst", "target"),
        "source_port": ("source_port", "src_port", "sport"),
        "destination_port": ("destination_port", "dest_port", "dport"),
        "protocol": ("protocol", "proto"),
        "user_name": ("user_name", "user", "username"),
        "process_name": ("process_name", "process", "app", "program"),
        "file_path": ("file_path", "path", "file"),
    }

    def parse(self, raw: str) -> dict | None:
        """Parsea un string JSON a diccionario normalizado.

        Argumentos:
            raw: String JSON con los campos del log.

        Retorna:
            Dict con campos normalizados, o None si el JSON es inválido.
        """
        if not raw or not raw.strip():
            return None

        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            logger.warning("JSON inválido: %s", raw[:100])
            return None

        if not isinstance(data, dict):
            return None

        # Construir el evento normalizado mapeando campos
        evento = {
            "source": self._extraer_campo(data, "source") or "unknown",
            "collector_type": "json",
            "event_timestamp": self._parsear_timestamp(data) or datetime.now(timezone.utc),
            "event_type": self._extraer_campo(data, "event_type") or "json_event",
            "severity": self._normalizar_severidad(self._extraer_campo(data, "severity")),
            "description": self._extraer_campo(data, "description") or raw,
            "source_ip": self._extraer_campo(data, "source_ip"),
            "destination_ip": self._extraer_campo(data, "destination_ip"),
            "source_port": self._extraer_int(data, "source_port"),
            "destination_port": self._extraer_int(data, "destination_port"),
            "protocol": self._extraer_campo(data, "protocol"),
            "user_name": self._extraer_campo(data, "user_name"),
            "process_name": self._extraer_campo(data, "process_name"),
            "file_path": self._extraer_campo(data, "file_path"),
            "raw_log": raw,
        }

        return evento

    def _extraer_campo(self, data: dict, campo: str) -> str | None:
        """Busca un campo en el JSON probando múltiples nombres posibles.

        Args:
            data: Diccionario del JSON parseado.
            campo: Nombre del campo en nuestro modelo.

        Returns:
            Valor del campo como string, o None.
        """
        for nombre in self.FIELD_MAP.get(campo, [campo]):
            valor = data.get(nombre)
            if valor is not None:
                return str(valor)
        return None

    def _extraer_int(self, data: dict, campo: str) -> int | None:
        """Busca un campo entero en el JSON probando múltiples nombres.

        Args:
            data: Diccionario del JSON parseado.
            campo: Nombre del campo en nuestro modelo.

        Returns:
            Valor entero, o None.
        """
        for nombre in self.FIELD_MAP.get(campo, [campo]):
            valor = data.get(nombre)
            if valor is not None:
                try:
                    return int(valor)
                except (ValueError, TypeError):
                    return None
        return None

    def _parsear_timestamp(self, data: dict) -> datetime | None:
        """Parsea el timestamp del JSON probando distintos formatos.

        Args:
            data: Diccionario del JSON parseado.

        Returns:
            datetime con timezone, o None.
        """
        # Campos de timestamp a probar
        for key in ("timestamp", "time", "date", "datetime", "event_timestamp", "@timestamp"):
            valor = data.get(key)
            if not valor:
                continue

            valor_str = str(valor)

            # Intentar formatos comunes
            formatos = [
                "%Y-%m-%dT%H:%M:%S.%fZ",      # ISO 8601 con microsegundos
                "%Y-%m-%dT%H:%M:%SZ",          # ISO 8601 sin microsegundos
                "%Y-%m-%dT%H:%M:%S.%f%z",      # ISO 8601 con timezone
                "%Y-%m-%d %H:%M:%S",            # Fecha hora simple
                "%Y-%m-%dT%H:%M:%S",            # ISO sin Z
            ]

            for fmt in formatos:
                try:
                    dt = datetime.strptime(valor_str, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    continue

        return None

    def _normalizar_severidad(self, severidad: str | None) -> str:
        """Convierte severidades de varios formatos a nuestro estándar.

        Args:
            severidad: Nivel de severidad en cualquier formato.

        Returns:
            Severidad normalizada: critical, high, medium, low, info.
        """
        if not severidad:
            return "info"

        severidad_lower = severidad.lower().strip()

        # Mapeo de valores comunes
        mapeo = {
            "critical": "critical", "crit": "critical", "emergency": "critical",
            "alert": "critical", "fatal": "critical",
            "high": "high", "error": "high", "err": "high",
            "medium": "medium", "warn": "medium", "warning": "medium",
            "low": "low", "notice": "low", "info": "info",
            "informational": "info", "debug": "info", "trace": "info",
        }

        return mapeo.get(severidad_lower, "info")
