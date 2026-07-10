"""Configuration models and TOML loading for the SentinelPy agent."""

from __future__ import annotations

import os
import tomllib
from typing import Optional

from pydantic import BaseModel


class WatchConfig(BaseModel):
    """Configuration for a single file/directory watch."""

    path: str
    parser: str = "syslog"
    pattern: Optional[str] = None


class AgentConfig(BaseModel):
    """Full agent configuration loaded from config.toml."""

    server_url: str
    api_key: str
    hostname: str
    poll_interval: float = 1.0
    batch_size: int = 50
    batch_interval: float = 5.0
    heartbeat_interval: float = 30.0
    queue_max_size: int = 10000
    watches: list[WatchConfig] = []
    verify_ssl: bool = True
    server_ca_path: Optional[str] = None

    @classmethod
    def from_toml(cls, path: str) -> "AgentConfig":
        """Load and validate configuration from a TOML file.

        The TOML file may use nested sections like [watcher] and [sender]
        whose keys are flattened into the top-level model.

        Supports environment variable overrides:
        - ``SENTINEL_VERIFY_SSL`` — overrides ``verify_ssl``
        """
        with open(path, "rb") as f:
            data = tomllib.load(f)

        # Flatten known subsections into the top level
        for section in ("watcher", "sender", "queue"):
            if section in data:
                data.update(data[section])
                del data[section]

        config = cls(**data)

        # Env var overrides (SENTINEL_ prefix)
        env_map = {
            "SENTINEL_SERVER_URL": "server_url",
            "SENTINEL_API_KEY": "api_key",
            "SENTINEL_HOSTNAME": "hostname",
        }
        for env_key, field in env_map.items():
            val = os.environ.get(env_key)
            if val:
                setattr(config, field, val)

        verify_ssl_env = os.environ.get("SENTINEL_VERIFY_SSL")
        if verify_ssl_env is not None:
            config.verify_ssl = verify_ssl_env.lower() in ("1", "true", "yes")

        return config
