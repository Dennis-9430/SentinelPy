"""Parsers de logs: convierten logs crudos al formato normalizado.

Cada parser entiende un formato específico y extrae los campos
comunes para almacenarlos como NormalizedEvent.
"""


class SyslogParser:
    """Parser de syslog: entiende RFC 3164 y RFC 5424.

    RFC 3164 (BSD): formato clásico "<PRI>timestamp hostname app[PID]: mensaje"
    RFC 5424 (ISO): formato estructurado con campos nombrados
    """

    def parse(self, raw: str) -> dict | None:
        """Convierte una línea de syslog a diccionario normalizado.

        Argumentos:
            raw: Línea de texto cruda del syslog.

        Retorna:
            Dict con campos normalizados, o None si no se pudo parsear.
        """
        raise NotImplementedError("Fase 2: implementar parser syslog")


class JSONParser:
    """Parser de logs en formato JSON.

    Útil para logs modernos que ya vienen estructurados (ej: Docker, aplicaciones).
    """

    def parse(self, raw: str) -> dict | None:
        """Parsea un string JSON a diccionario normalizado.

        Argumentos:
            raw: String JSON con los campos del log.

        Retorna:
            Dict con campos normalizados, o None si el JSON es inválido.
        """
        raise NotImplementedError("Fase 2: implementar parser JSON")
