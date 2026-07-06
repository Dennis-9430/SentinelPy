"""Tests for agent.sender — HTTP batch sender with backoff and heartbeat."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

from agent.sender import EventSender


@pytest.fixture
def sender():
    """EventSender with mocked httpx client."""
    s = EventSender(
        server_url="http://localhost:8000",
        api_key="spy_test_key",
        hostname="test-host",
        batch_size=10,
        batch_interval=0.05,
        heartbeat_interval=0.1,
        os_name="linux",
        agent_version="1.0.0",
    )
    # Replace the real client with a mock
    s._http_client = AsyncMock()
    s._http_client.is_closed = MagicMock(return_value=False)
    s._http_client.aclose = AsyncMock()
    return s


class TestEventSender:
    """EventSender with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_send_batch_success(self, sender):
        """send_batch returns True on 200."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"processed": 2, "ids": ["a", "b"]})
        sender._http_client.post = AsyncMock(return_value=mock_response)

        events = [{"event_type": "login"}, {"event_type": "logout"}]
        result = await sender.send_batch(events)
        assert result is True

        sender._http_client.post.assert_called_once_with(
            "http://localhost:8000/api/v2/events",
            json={"events": events, "hostname": "test-host"},
            headers={"Authorization": "Bearer spy_test_key"},
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_send_batch_server_error_retries(self, sender):
        """send_batch retries on 500 and uses backoff."""
        mock_fail = MagicMock()
        mock_fail.status_code = 500
        mock_success = MagicMock()
        mock_success.status_code = 200

        sender._http_client.post = AsyncMock(side_effect=[mock_fail, mock_success])

        events = [{"event_type": "test"}]
        result = await sender.send_batch(events)
        assert result is True
        # Called twice (first fails, second succeeds)
        assert sender._http_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_batch_http_error_retries(self, sender):
        """send_batch retries on httpx transport errors."""
        import httpx
        sender._http_client.post = AsyncMock(
            side_effect=[httpx.ConnectError("Connection refused"), MagicMock(status_code=200)]
        )

        events = [{"event_type": "test"}]
        result = await sender.send_batch(events)
        assert result is True
        assert sender._http_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_batch_max_retries(self, sender):
        """send_batch stops retrying after exhausting attempts."""
        mock_fail = MagicMock()
        mock_fail.status_code = 500

        sender._http_client.post = AsyncMock(return_value=mock_fail)

        events = [{"event_type": "test"}]
        result = await sender.send_batch(events)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_batch_unauthorized_stops(self, sender):
        """send_batch returns False on 401 without retry."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        sender._http_client.post = AsyncMock(return_value=mock_response)

        events = [{"event_type": "test"}]
        result = await sender.send_batch(events)
        assert result is False
        # Only called once (no retry on 401)
        assert sender._http_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_send_heartbeat(self, sender):
        """send_heartbeat POSTs to /api/v2/agent/heartbeat with hostname, os, agent_version."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        sender._http_client.post = AsyncMock(return_value=mock_response)

        result = await sender.send_heartbeat()
        assert result is True

        sender._http_client.post.assert_called_once_with(
            "http://localhost:8000/api/v2/agent/heartbeat",
            json={"hostname": "test-host", "os": "linux", "agent_version": "1.0.0"},
            headers={"Authorization": "Bearer spy_test_key"},
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_send_heartbeat_uses_defaults_when_not_provided(self):
        """send_heartbeat uses 'unknown' and '0.1.0' defaults when not provided."""
        s = EventSender(
            server_url="http://localhost:8000",
            api_key="spy_test_key",
            hostname="default-host",
        )
        s._http_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        s._http_client.post = AsyncMock(return_value=mock_response)

        result = await s.send_heartbeat()
        assert result is True

        s._http_client.post.assert_called_once_with(
            "http://localhost:8000/api/v2/agent/heartbeat",
            json={"hostname": "default-host", "os": "unknown", "agent_version": "0.1.0"},
            headers={"Authorization": "Bearer spy_test_key"},
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_backoff_increases(self, sender):
        """Backoff delay increases with each retry."""
        delays = []
        for attempt in range(6):
            delay = sender._get_backoff(attempt)
            delays.append(delay)
        # Each backoff should be larger than the last (with jitter, approximate)
        assert delays[0] < delays[1] < delays[2] < delays[3] < delays[4]

    @pytest.mark.asyncio
    async def test_backoff_capped_at_30(self, sender):
        """Backoff caps at 30 seconds."""
        delay = sender._get_backoff(100)
        assert delay <= 30.0

    @pytest.mark.asyncio
    async def test_batch_accumulator(self, sender):
        """accumulate adds events and flush returns them at batch_size."""
        sender.buffer = []
        # Add events below batch_size — should not auto-flush
        sender.accumulate({"n": 1})
        sender.accumulate({"n": 2})
        assert len(sender.buffer) == 2

        # Flush manually
        batch = sender.flush()
        assert len(batch) == 2
        assert sender.buffer == []

    @pytest.mark.asyncio
    async def test_batch_flush_empty(self, sender):
        """flush returns empty list when buffer is empty."""
        sender.buffer = []
        assert sender.flush() == []

    @pytest.mark.asyncio
    async def test_reconnect(self, sender):
        """reconnect closes old client and creates new one."""
        old_client = sender._http_client
        await sender.reconnect()
        assert sender._http_client is not old_client
        old_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close(self, sender):
        """close cleans up the client."""
        old_client = sender._http_client
        await sender.close()
        assert sender._http_client is None
        old_client.aclose.assert_awaited_once()
