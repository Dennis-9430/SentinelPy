"""HTTP event sender with exponential backoff, batching, and heartbeat.

Sends events to the SentinelPy server via POST /api/v2/events and
periodic heartbeats via POST /api/v2/agent/heartbeat.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class EventSender:
    """Async HTTP sender with backoff, batching, and heartbeat support.

    Accumulates events in a buffer and flushes them either when the buffer
    reaches batch_size or when flush() is called (e.g. via timer).
    """

    def __init__(
        self,
        server_url: str,
        api_key: str,
        hostname: str,
        batch_size: int = 50,
        batch_interval: float = 5.0,
        heartbeat_interval: float = 30.0,
        os_name: str = "unknown",
        agent_version: str = "0.1.0",
        verify_ssl: bool = True,
        ca_path: str | None = None,
    ):
        self._server_url = server_url.rstrip("/")
        self._api_key = api_key
        self._hostname = hostname
        self._os_name = os_name
        self._agent_version = agent_version
        self._batch_size = batch_size
        self._batch_interval = batch_interval
        self._heartbeat_interval = heartbeat_interval
        self._verify_ssl = verify_ssl
        self._ca_path = ca_path

        self.buffer: list[dict] = []
        self._http_client: Optional[httpx.AsyncClient] = None
        self._max_retries = 5

    def _make_client(self) -> httpx.AsyncClient:
        """Create a new HTTP client with the configured TLS settings."""
        kwargs: dict[str, Any] = {"timeout": 30.0}
        if not self._verify_ssl:
            kwargs["verify"] = False
            logger.warning(
                "SSL verification is disabled — do not use in production"
            )
        elif self._ca_path is not None:
            kwargs["verify"] = self._ca_path
        return httpx.AsyncClient(**kwargs)

    def _get_client(self) -> httpx.AsyncClient:
        """Return the HTTP client, creating it lazily if needed."""
        if self._http_client is None:
            self._http_client = self._make_client()
        return self._http_client

    # ── Batching ─────────────────────────────────────────────────────────────

    def accumulate(self, event: dict) -> None:
        """Add an event to the buffer for batched sending."""
        self.buffer.append(event)

    def flush(self) -> list[dict]:
        """Return and clear the current buffer contents.

        Returns:
            The list of accumulated events, or empty list.
        """
        batch = self.buffer[:]
        self.buffer.clear()
        return batch

    # ── HTTP operations ──────────────────────────────────────────────────────

    # Field aliases: map common log field names to the API schema
    _FIELD_ALIASES = {
        "level": "severity",
        "host": "source",
        "hostname": "source",
        "src_ip": "source_ip",
        "dst_ip": "destination_ip",
        "src_port": "source_port",
        "dst_port": "destination_port",
        "proc": "process_name",
    }

    def _normalize_event(self, event: dict) -> dict:
        """Normalize field names using known aliases.

        The server expects specific field names (severity, source_ip, etc).
        Many log formats use different names (level, host, src_ip, etc).
        This maps aliases to the canonical names without overwriting
        fields that are already present.
        """
        normalized = dict(event)
        for alias, canonical in self._FIELD_ALIASES.items():
            if alias in normalized and canonical not in normalized:
                normalized[canonical] = normalized.pop(alias)
        return normalized

    async def send_batch(self, events: list[dict]) -> bool:
        """Send a batch of events to the server with retry logic.

        Args:
            events: List of event dicts to send.

        Returns:
            True if the batch was sent successfully, False if all retries failed.
        """
        client = self._get_client()

        # Normalize field names before sending
        normalized = [self._normalize_event(e) for e in events]

        for attempt in range(self._max_retries + 1):
            try:
                response = await client.post(
                    f"{self._server_url}/api/v2/events",
                    json={"events": normalized, "hostname": self._hostname},
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=30,
                )

                if response.status_code == 200:
                    return True

                # 400 Bad Request — log and don't retry (bad data)
                if response.status_code == 400:
                    logger.warning(
                        "Batch rejected (400): %s",
                        response.text[:200],
                    )
                    return False

                # 401/403 means the API key is invalid — don't retry
                if response.status_code in (401, 403):
                    return False

                # Server errors — retry
                if attempt < self._max_retries:
                    delay = self._get_backoff(attempt)
                    await asyncio.sleep(delay)
                    continue
                return False

            except (httpx.HTTPError, OSError):
                if attempt < self._max_retries:
                    delay = self._get_backoff(attempt)
                    await asyncio.sleep(delay)
                    continue
                return False

    async def send_heartbeat(self) -> bool:
        """Send a heartbeat to the server.

        Returns:
            True if the heartbeat was sent successfully.
        """
        client = self._get_client()

        try:
            response = await client.post(
                f"{self._server_url}/api/v2/agent/heartbeat",
                json={
                    "hostname": self._hostname,
                    "os": self._os_name,
                    "agent_version": self._agent_version,
                },
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=30,
            )
            return response.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    async def reconnect(self) -> None:
        """Close the current client and create a fresh one."""
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception:
                pass
        self._http_client = self._make_client()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception:
                pass
            self._http_client = None

    # ── Backoff ──────────────────────────────────────────────────────────────

    @staticmethod
    def _get_backoff(attempt: int) -> float:
        """Calculate backoff delay with jitter.

        Base delays: 0.5s, 1s, 2s, 4s, 8s, 16s, capped at 30s.
        Jitter: ±20% random variation.

        Args:
            attempt: Zero-based attempt number.

        Returns:
            Delay in seconds (float).
        """
        base = min(0.5 * (2**attempt), 30.0)
        jitter = base * 0.2
        return min(base + random.uniform(-jitter, jitter), 30.0)
