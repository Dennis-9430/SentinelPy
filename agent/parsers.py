"""Log line parsers: syslog RFC 3164, JSON lines, and configurable regex."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Optional


class ParseError(Exception):
    """Raised when parser construction or parsing fails."""


class BaseParser(ABC):
    """Abstract base for all log line parsers."""

    @abstractmethod
    def parse(self, line: str) -> Optional[dict]:
        """Parse a single log line into a structured dict, or None if unmatched."""


# ── RFC 3164 Syslog ──────────────────────────────────────────────────────────

# Groups: timestamp, hostname, process (optional [pid]), message
_SYSLOG_RE = re.compile(
    r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(\S+)\s+"
    r"(\S+?)(?:\[(\d+)\])?\:\s*"
    r"(.*)$"
)


class SyslogParser(BaseParser):
    """Parser for syslog messages following RFC 3164."""

    def parse(self, line: str) -> Optional[dict]:
        if not line.strip():
            return None
        m = _SYSLOG_RE.match(line)
        if not m:
            return None
        return {
            "timestamp": m.group(1),
            "hostname": m.group(2),
            "process": m.group(3),
            "pid": m.group(4),
            "message": m.group(5),
        }


# ── JSON Lines ───────────────────────────────────────────────────────────────


class JSONParser(BaseParser):
    """Parser for JSON-formatted log lines."""

    def parse(self, line: str) -> Optional[dict]:
        stripped = line.strip()
        if not stripped:
            return None
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None
        return obj


# ── Configurable Regex ───────────────────────────────────────────────────────


class RegexParser(BaseParser):
    """Parser using a configurable regex with named capture groups."""

    def __init__(self, pattern: str):
        self._pattern = re.compile(pattern)

    def parse(self, line: str) -> Optional[dict]:
        m = self._pattern.match(line)
        if not m:
            return None
        return m.groupdict() if m.groupdict() else {"0": m.group(0)}


# ── Factory ──────────────────────────────────────────────────────────────────


def get_parser(name: str, **kwargs) -> BaseParser:
    """Return a parser instance by name.

    Args:
        name: One of "syslog", "json", or "regex".
        **kwargs: Passed to the parser constructor (e.g. pattern for regex).

    Returns:
        A BaseParser instance.

    Raises:
        ParseError: If the name is unknown or required arguments are missing.
    """
    name = name.strip().lower()
    if name == "syslog":
        return SyslogParser()
    elif name == "json":
        return JSONParser()
    elif name == "regex":
        pattern = kwargs.get("pattern")
        if not pattern:
            raise ParseError("Regex parser requires a 'pattern' argument")
        return RegexParser(pattern)
    raise ParseError(f"Unknown parser: {name}")
