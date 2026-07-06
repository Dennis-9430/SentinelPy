"""Tests for agent.parsers — syslog, JSON, and regex parsers."""

import pytest
import json

from agent.parsers import (
    SyslogParser,
    JSONParser,
    RegexParser,
    get_parser,
    ParseError,
)


class TestSyslogParser:
    """Syslog RFC 3164 parsing."""

    def setup_method(self):
        self.parser = SyslogParser()

    def test_rfc3164_standard(self):
        """Parse standard RFC 3164 syslog message."""
        line = "Oct  9 22:33:20 myhost sshd[12345]: Failed password for root from 192.168.1.100 port 22 ssh2"
        result = self.parser.parse(line)
        assert result is not None
        assert result["timestamp"] == "Oct  9 22:33:20"
        assert result["hostname"] == "myhost"
        assert result["process"] == "sshd"
        assert result["pid"] == "12345"
        assert result["message"] == "Failed password for root from 192.168.1.100 port 22 ssh2"

    def test_rfc3164_no_pid(self):
        """Parse RFC 3164 message without PID."""
        line = "Oct  9 22:33:20 myhost sudo: pam_unix(sudo:auth): authentication failure"
        result = self.parser.parse(line)
        assert result is not None
        assert result["hostname"] == "myhost"
        assert result["process"] == "sudo"
        assert result["pid"] is None

    def test_rfc3164_invalid(self):
        """Return None for non-syslog lines."""
        result = self.parser.parse("this is not syslog at all")
        assert result is None

    def test_rfc3164_empty(self):
        """Return None for empty string."""
        result = self.parser.parse("")
        assert result is None


class TestJSONParser:
    """JSON lines parsing."""

    def setup_method(self):
        self.parser = JSONParser()

    def test_valid_json_object(self):
        """Parse a valid JSON object line."""
        result = self.parser.parse('{"level": "error", "message": "disk full", "host": "srv01"}')
        assert result is not None
        assert result["level"] == "error"
        assert result["message"] == "disk full"
        assert result["host"] == "srv01"

    def test_valid_json_array(self):
        """Return None for JSON array (not an object)."""
        result = self.parser.parse('[1, 2, 3]')
        assert result is None

    def test_valid_json_primitive(self):
        """Return None for JSON primitive."""
        result = self.parser.parse('"just a string"')
        assert result is None

    def test_invalid_json(self):
        """Return None for malformed JSON."""
        result = self.parser.parse('{"broken": true')
        assert result is None

    def test_empty(self):
        """Return None for empty string."""
        result = self.parser.parse("")
        assert result is None

    def test_extra_whitespace(self):
        """Handles leading/trailing whitespace."""
        result = self.parser.parse('  {"key": "value"}  ')
        assert result is not None
        assert result["key"] == "value"


class TestRegexParser:
    """Regex-based parsing with named groups."""

    def test_match_with_named_groups(self):
        """Parse line using regex with named capture groups."""
        parser = RegexParser(pattern=r"^(?P<timestamp>\S+)\s+(?P<level>\S+)\s+(?P<message>.*)$")
        result = parser.parse("2024-01-15T10:30:00 ERROR something went wrong")
        assert result is not None
        assert result["timestamp"] == "2024-01-15T10:30:00"
        assert result["level"] == "ERROR"
        assert result["message"] == "something went wrong"

    def test_no_match(self):
        """Return None when regex does not match."""
        parser = RegexParser(pattern=r"^(?P<code>\d+)$")
        result = parser.parse("not a number")
        assert result is None

    def test_empty(self):
        """Return None for empty string."""
        parser = RegexParser(pattern=r"^(?P<x>.*)$")
        result = parser.parse("")
        assert result is not None
        assert result["x"] == ""

    def test_no_named_groups(self):
        """Return full match dict even without named groups."""
        parser = RegexParser(pattern=r"^(ERROR|INFO|WARN)")
        result = parser.parse("ERROR something happened")
        assert result is not None
        assert result["0"] == "ERROR"


class TestGetParser:
    """Parser factory."""

    def test_syslog_parser(self):
        """get_parser returns SyslogParser for 'syslog'."""
        parser = get_parser("syslog")
        assert isinstance(parser, SyslogParser)

    def test_json_parser(self):
        """get_parser returns JSONParser for 'json'."""
        parser = get_parser("json")
        assert isinstance(parser, JSONParser)

    def test_regex_parser(self):
        """get_parser returns RegexParser for 'regex' with pattern."""
        parser = get_parser("regex", pattern=r"^test$")
        assert isinstance(parser, RegexParser)

    def test_regex_parser_no_pattern(self):
        """get_parser raises ParseError for 'regex' without pattern."""
        with pytest.raises(ParseError, match="pattern"):
            get_parser("regex")

    def test_unknown_parser(self):
        """get_parser raises ParseError for unknown parser type."""
        with pytest.raises(ParseError, match="Unknown parser"):
            get_parser("unknown")
