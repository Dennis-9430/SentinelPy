"""Log parsers: normalize raw logs into the Common Information Model."""


class SyslogParser:
    """Parses RFC 3164 and RFC 5424 syslog messages."""

    def parse(self, raw: str) -> dict | None:
        """Parse a raw syslog line into normalized fields."""
        raise NotImplementedError("Fase 2: implementar parser syslog")


class JSONParser:
    """Parses JSON-format logs."""

    def parse(self, raw: str) -> dict | None:
        """Parse a JSON log string."""
        raise NotImplementedError("Fase 2: implementar parser JSON")
