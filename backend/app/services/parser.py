"""Log parsers: convert raw logs to the normalized format.

Each parser understands a specific format and extracts the common
fields to store them as NormalizedEvent.
"""

import json
import logging
import re
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# ── Map syslog severity to SentinelPy severity ─────────────────────
# Syslog levels 0-7 map to our model
SYSLOG_SEVERITY_MAP = {
    0: "critical",  # Emergency
    1: "critical",  # Alert
    2: "critical",  # Critical
    3: "high",  # Error
    4: "medium",  # Warning
    5: "low",  # Notice
    6: "info",  # Informational
    7: "info",  # Debug
}

# ── Syslog facility map ─────────────────────────────────────────────
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

# ── Regex for RFC 3164 (BSD syslog) ─────────────────────────────────────
# Format: <PRI>Timestamp Hostname App[PID]: Message
# Also supports without PID: <PRI>Timestamp Hostname App: Message
RFC3164_PATTERN = re.compile(
    r"^<(\d{1,3})>"  # 1: Priority (facility*8 + severity)
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"  # 2: Month
    r"(\d{1,2})\s+"  # 3: Day
    r"(\d{2}:\d{2}:\d{2})\s+"  # 4: Time
    r"(\S+)\s+"  # 5: Hostname
    r"(\S+?)"  # 6: App name
    r"(?:\[(\d+)\])?"  # 7: PID (optional)
    r":\s*(.*)"  # 8: Message
)


class SyslogParser:
    """Syslog parser: understands RFC 3164 (BSD).

    RFC 3164: "<PRI>Timestamp Hostname App[PID]: Message"

    Example:
        <30>Oct  9 22:33:20 myhost sshd[12345]: Failed password for root from 192.168.1.100 port 22 ssh2
    """

    def parse(self, raw: str) -> dict | None:
        """Convert a syslog line to a normalized dictionary.

        Args:
            raw: Raw text line from syslog.

        Returns:
            Dict with normalized fields ready to create a NormalizedEvent,
            or None if it could not be parsed.
        """
        if not raw or not raw.strip():
            return None

        # Try to match RFC 3164
        match = RFC3164_PATTERN.match(raw.strip())
        if not match:
            logger.warning(
                "Could not parse syslog message (unrecognized format): %s",
                raw[:100],
            )
            return None

        # Extract groups
        priority = int(match.group(1))
        mes = match.group(2)
        dia = match.group(3)
        hora = match.group(4)
        hostname = match.group(5)
        app_name = match.group(6)
        match.group(7)  # May be None
        mensaje = match.group(8)

        # Compute facility and severity from the priority
        # Syslog: PRI = facility * 8 + severity
        priority // 8
        severity_code = priority % 8

        # Build timestamp combining the syslog date with the current year
        # RFC 3164 does not include the year, so we use the current year
        año_actual = datetime.now(UTC).year
        timestamp_str = f"{mes} {dia} {hora} {año_actual}"

        try:
            # Parse syslog-style date: "Oct  9 22:33:20 2026"
            event_timestamp = datetime.strptime(timestamp_str, "%b %d %H:%M:%S %Y")
            event_timestamp = event_timestamp.replace(tzinfo=UTC)
        except ValueError:
            # If it fails, use the current timestamp
            logger.warning("Could not parse syslog timestamp, using current time")
            event_timestamp = datetime.now(UTC)

        # Determine event type based on the app name
        event_type = self._detectar_tipo_evento(app_name, mensaje)

        # Extract IPs from the message if present
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
        """Detect the event type based on the application and message.

        Args:
            app_name: Name of the application that generated the log.
            mensaje: Message content.

        Returns:
            String with the normalized event type.
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

        # If it could not be determined, generic
        return "unknown"

    def _extraer_ips(self, mensaje: str) -> tuple:
        """Extract IP addresses from the message.

        Args:
            mensaje: Message text.

        Returns:
            Tuple (source_ip, destination_ip).
        """
        # Simple IPv4 pattern
        ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", mensaje)

        if len(ips) >= 2:
            return ips[0], ips[1]
        elif len(ips) == 1:
            return ips[0], None
        return None, None


class JSONParser:
    """Parser for logs in JSON format.

    Useful for modern logs that are already structured (e.g. Docker, applications).
    """

    # Map JSON field names to our normalized model
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
        """Parse a JSON string into a normalized dictionary.

        Args:
            raw: JSON string with the log fields.

        Returns:
            Dict with normalized fields, or None if the JSON is invalid.
        """
        if not raw or not raw.strip():
            return None

        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            logger.warning("Invalid JSON: %s", raw[:100])
            return None

        if not isinstance(data, dict):
            return None

        # Build the normalized event by mapping fields
        evento = {
            "source": self._extraer_campo(data, "source"),
            "collector_type": "json",
            "event_timestamp": self._parsear_timestamp(data) or datetime.now(UTC),
            "event_type": self._extraer_campo(data, "event_type") or "json_event",
            "severity": self._normalizar_severidad(
                self._extraer_campo(data, "severity")
            ),
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
        """Look up a field in the JSON trying multiple possible names.

        Args:
            data: Dictionary of the parsed JSON.
            campo: Field name in our model.

        Returns:
            Field value as a string, or None.
        """
        for nombre in self.FIELD_MAP.get(campo, [campo]):
            valor = data.get(nombre)
            if valor is not None:
                return str(valor)
        return None

    def _extraer_int(self, data: dict, campo: str) -> int | None:
        """Look up an integer field in the JSON trying multiple names.

        Args:
            data: Dictionary of the parsed JSON.
            campo: Field name in our model.

        Returns:
            Integer value, or None.
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
        """Parse the timestamp from the JSON trying different formats.

        Args:
            data: Dictionary of the parsed JSON.

        Returns:
            datetime with timezone, or None.
        """
        # Timestamp fields to try
        for key in (
            "timestamp",
            "time",
            "date",
            "datetime",
            "event_timestamp",
            "@timestamp",
        ):
            valor = data.get(key)
            if not valor:
                continue

            valor_str = str(valor)

            # Try common formats
            formatos = [
                "%Y-%m-%dT%H:%M:%S.%fZ",  # ISO 8601 with microseconds
                "%Y-%m-%dT%H:%M:%SZ",  # ISO 8601 without microseconds
                "%Y-%m-%dT%H:%M:%S.%f%z",  # ISO 8601 with timezone
                "%Y-%m-%d %H:%M:%S",  # Simple date time
                "%Y-%m-%dT%H:%M:%S",  # ISO without Z
            ]

            for fmt in formatos:
                try:
                    dt = datetime.strptime(valor_str, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)
                    return dt
                except ValueError:
                    continue

        return None

    def _normalizar_severidad(self, severidad: str | None) -> str:
        """Convert severities from various formats to our standard.

        Args:
            severidad: Severity level in any format.

        Returns:
            Normalized severity: critical, high, medium, low, info.
        """
        if not severidad:
            return "info"

        severidad_lower = severidad.lower().strip()

        # Map of common values
        mapeo = {
            "critical": "critical",
            "crit": "critical",
            "emergency": "critical",
            "alert": "critical",
            "fatal": "critical",
            "high": "high",
            "error": "high",
            "err": "high",
            "medium": "medium",
            "warn": "medium",
            "warning": "medium",
            "low": "low",
            "notice": "low",
            "info": "info",
            "informational": "info",
            "debug": "info",
            "trace": "info",
        }

        return mapeo.get(severidad_lower, "info")
