"""Tests for agent.agent — asyncio main loop wiring watcher→parser→queue→sender."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4

from agent.agent import Agent


@pytest.fixture
def mock_config():
    """Minimal agent configuration."""
    config = MagicMock()
    config.server_url = "http://localhost:8000"
    config.api_key = "spy_test"
    config.hostname = "test-host"
    config.poll_interval = 0.05
    config.batch_size = 10
    config.batch_interval = 0.05
    config.heartbeat_interval = 0.1
    config.queue_max_size = 100
    config.watches = []
    return config


@pytest.fixture
def agent(mock_config):
    """Agent instance with all components mocked."""
    a = Agent(config=mock_config)
    # Replace components with mocks
    a._watcher = MagicMock()
    a._watcher.watch = MagicMock()
    a._watcher.start = MagicMock()
    a._watcher.poll = MagicMock(return_value={})
    a._watcher.stop = MagicMock()

    a._parsers = {}  # watch_path → parser mock

    a._queue = MagicMock()
    a._queue.enqueue = MagicMock()
    a._queue.dequeue = MagicMock(return_value=[])
    a._queue.mark_sent = MagicMock()
    a._queue.count = MagicMock(return_value=0)
    a._queue.close = MagicMock()

    a._sender = AsyncMock()
    a._sender.accumulate = MagicMock()
    a._sender.flush = MagicMock(return_value=[])
    a._sender.send_batch = AsyncMock(return_value=True)
    a._sender.send_heartbeat = AsyncMock(return_value=True)
    a._sender.close = AsyncMock()
    return a


class TestAgent:
    """Agent lifecycle and wiring."""

    @pytest.mark.asyncio
    async def test_init_without_watches(self, agent):
        """Agent starts without watches configured."""
        agent._watcher.watch.assert_not_called()

    @pytest.mark.asyncio
    async def test_init_with_watches(self, mock_config):
        """Agent registers watches from config."""
        mock_config.watches = [
            MagicMock(path="/var/log/syslog", parser="syslog", pattern=None),
            MagicMock(path="/var/log/app.json", parser="json", pattern=None),
        ]
        a = Agent(config=mock_config)
        # After init, watches should be registered
        assert "/var/log/syslog" in a._parsers
        assert "/var/log/app.json" in a._parsers

    @pytest.mark.asyncio
    async def test_parse_and_enqueue(self, agent):
        """_process_lines parses lines and enqueues results."""
        agent._parsers = {
            "/var/log/test.log": MagicMock(parse=MagicMock(return_value={"event_type": "test"})),
        }
        await agent._process_lines("/var/log/test.log", ["line1\n", "line2\n"])
        assert agent._parsers["/var/log/test.log"].parse.call_count == 2
        assert agent._queue.enqueue.call_count == 2

    @pytest.mark.asyncio
    async def test_parse_returns_none_skips_enqueue(self, agent):
        """Lines that return None from parser are skipped."""
        parser = MagicMock()
        parser.parse = MagicMock(return_value=None)
        agent._parsers = {"/var/log/test.log": parser}
        await agent._process_lines("/var/log/test.log", ["line1\n"])
        agent._queue.enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_cycle_calls_watcher_and_processes(self, agent):
        """_poll_cycle reads from watcher and processes lines."""
        agent._watcher.poll = MagicMock(return_value={"/var/log/test.log": ["line1\n"]})
        parser = MagicMock()
        parser.parse = MagicMock(return_value={"event": "parsed"})
        agent._parsers = {"/var/log/test.log": parser}

        await agent._poll_cycle()
        parser.parse.assert_called_once_with("line1\n")
        agent._queue.enqueue.assert_called_once_with({"event": "parsed"})

    @pytest.mark.asyncio
    async def test_send_cycle_delegates_to_sender(self, agent):
        """_send_cycle dequeues, sends batch, and marks sent."""
        agent._queue.dequeue = MagicMock(return_value=[
            {"id": 1, "event_data": {"type": "a"}},
            {"id": 2, "event_data": {"type": "b"}},
        ])
        agent._sender.send_batch = AsyncMock(return_value=True)

        await agent._send_cycle()

        agent._sender.send_batch.assert_called_once_with(
            [{"type": "a"}, {"type": "b"}]
        )
        agent._queue.mark_sent.assert_called_once_with([1, 2])

    @pytest.mark.asyncio
    async def test_send_cycle_does_not_mark_on_failure(self, agent):
        """Mark_sent is not called when send_batch fails."""
        agent._queue.dequeue = MagicMock(return_value=[
            {"id": 1, "event_data": {"type": "a"}},
        ])
        agent._sender.send_batch = AsyncMock(return_value=False)

        await agent._send_cycle()

        agent._queue.mark_sent.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_cycle_empty_queue(self, agent):
        """Send cycle does nothing when queue is empty."""
        agent._queue.dequeue = MagicMock(return_value=[])
        await agent._send_cycle()
        agent._sender.send_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_heartbeat_cycle(self, agent):
        """_heartbeat_cycle calls sender.send_heartbeat."""
        await agent._heartbeat_cycle()
        agent._sender.send_heartbeat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_stop(self, agent):
        """Agent starts and stops cleanly."""
        # Run the agent briefly then stop
        run_task = asyncio.create_task(agent.run())
        await asyncio.sleep(0.1)
        await agent.stop()
        await run_task

        agent._watcher.start.assert_called_once()
        agent._watcher.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_context_manager(self, agent):
        """Agent works as async context manager."""
        async with agent:
            pass

        agent._watcher.start.assert_called_once()
        agent._watcher.stop.assert_called_once()
