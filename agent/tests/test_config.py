"""Tests for agent.config — Pydantic models and TOML loading."""

import pytest
import tempfile
import os
from pathlib import Path

from agent.config import AgentConfig, WatchConfig


class TestWatchConfig:
    """WatchConfig validation."""

    def test_minimal(self):
        """WatchConfig with only required fields."""
        wc = WatchConfig(path="/var/log/syslog", parser="syslog")
        assert wc.path == "/var/log/syslog"
        assert wc.parser == "syslog"
        assert wc.pattern is None

    def test_with_regex_pattern(self):
        """WatchConfig with regex parser and pattern."""
        wc = WatchConfig(
            path="/var/log/custom.log",
            parser="regex",
            pattern=r"^(?P<ts>\S+)\s+(?P<msg>.*)$",
        )
        assert wc.parser == "regex"
        assert wc.pattern is not None


class TestAgentConfig:
    """AgentConfig loading and defaults."""

    def test_minimal_required(self):
        """AgentConfig with only required fields applies defaults."""
        config = AgentConfig(
            server_url="http://localhost:8000",
            api_key="spy_test_key",
            hostname="test-host",
        )
        assert config.server_url == "http://localhost:8000"
        assert config.api_key == "spy_test_key"
        assert config.hostname == "test-host"
        assert config.poll_interval == 1.0
        assert config.batch_size == 50
        assert config.batch_interval == 5.0
        assert config.heartbeat_interval == 30.0
        assert config.queue_max_size == 10000
        assert config.watches == []

    def test_with_watches(self):
        """AgentConfig with watches parses each WatchConfig."""
        config = AgentConfig(
            server_url="http://localhost:8000",
            api_key="spy_key",
            hostname="srv-01",
            watches=[
                WatchConfig(path="/var/log/auth.log", parser="syslog"),
                WatchConfig(path="/var/log/app.json", parser="json"),
            ],
        )
        assert len(config.watches) == 2
        assert config.watches[0].path == "/var/log/auth.log"
        assert config.watches[1].parser == "json"

    def test_from_toml_valid(self):
        """from_toml loads and validates a valid TOML file."""
        toml_content = '''
server_url = "http://localhost:8000"
api_key = "spy_mykey123"
hostname = "server-01"

[watcher]
poll_interval = 2.0

[sender]
batch_size = 100
batch_interval = 10.0
heartbeat_interval = 60.0
queue_max_size = 5000

[[watches]]
path = "/var/log/syslog"
parser = "syslog"

[[watches]]
path = "/var/log/app.json"
parser = "json"
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            tmp_path = f.name
        try:
            config = AgentConfig.from_toml(tmp_path)
            assert config.server_url == "http://localhost:8000"
            assert config.api_key == "spy_mykey123"
            assert config.hostname == "server-01"
            assert config.poll_interval == 2.0
            assert config.batch_size == 100
            assert config.queue_max_size == 5000
            assert len(config.watches) == 2
            assert config.watches[0].path == "/var/log/syslog"
            assert config.watches[1].parser == "json"
        finally:
            os.unlink(tmp_path)

    def test_from_toml_file_not_found(self):
        """from_toml raises FileNotFoundError for missing path."""
        with pytest.raises(FileNotFoundError):
            AgentConfig.from_toml("/nonexistent/path.toml")

    def test_from_toml_invalid_toml(self):
        """from_toml raises tomllib.TOMLDecodeError for bad TOML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("this is not = toml {{{")
            tmp_path = f.name
        try:
            import tomllib
            with pytest.raises(tomllib.TOMLDecodeError):
                AgentConfig.from_toml(tmp_path)
        finally:
            os.unlink(tmp_path)
