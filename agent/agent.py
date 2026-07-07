"""SentinelPy remote agent — main asyncio loop.

Wires together: watcher → parser → queue → sender
Runs concurrent cycles: polling, sending, heartbeat.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import signal
from typing import Optional

from agent.config import AgentConfig
from agent.parsers import get_parser
from agent.queue import EventQueue
from agent.sender import EventSender
from agent.watcher import get_watcher

logger = logging.getLogger("sentinel-agent")


class Agent:
    """Main agent orchestrator.

    Runs three concurrent asyncio tasks:
    - Poll cycle: watcher → parse → enqueue
    - Send cycle: dequeue → sender (batch HTTP)
    - Heartbeat cycle: periodic server keepalive
    """

    def __init__(self, config: AgentConfig):
        self._config = config
        self._running = False

        # Watcher
        self._watcher = get_watcher(poll_interval=config.poll_interval)

        # Parsers: one per watch path
        self._parsers: dict[str, object] = {}
        for watch in config.watches:
            kwargs = {}
            if watch.pattern:
                kwargs["pattern"] = watch.pattern
            parser = get_parser(watch.parser, **kwargs)
            self._parsers[watch.path] = parser
            self._watcher.watch(watch.path)

        # Queue
        self._queue = EventQueue(
            db_path=f"agent-{config.hostname}.db",
            max_size=config.queue_max_size,
        )

        # Sender
        self._sender = EventSender(
            server_url=config.server_url,
            api_key=config.api_key,
            hostname=config.hostname,
            batch_size=config.batch_size,
            batch_interval=config.batch_interval,
            heartbeat_interval=config.heartbeat_interval,
            os_name=platform.system().lower() or "unknown",
            agent_version="1.0.0",
            verify_ssl=config.verify_ssl,
            ca_path=config.server_ca_path,
        )

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def __aenter__(self):
        await self.run()
        return self

    async def __aexit__(self, *args):
        await self.stop()

    async def run(self) -> None:
        """Start the agent's main loop with concurrent tasks."""
        self._running = True
        self._watcher.start()

        # Create concurrent tasks
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._send_task = asyncio.create_task(self._send_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info("Agent started — watching %d file(s)", len(self._parsers))

    async def stop(self) -> None:
        """Gracefully stop all loops and clean up."""
        self._running = False

        # Cancel tasks
        for task_name in ("_poll_task", "_send_task", "_heartbeat_task"):
            task = getattr(self, task_name, None)
            if task and not task.done():
                task.cancel()

        # Wait for cancellation
        if hasattr(self, "_poll_task"):
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        self._poll_task, self._send_task, self._heartbeat_task,
                        return_exceptions=True,
                    ),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                logger.warning("Task cancellation timed out")

        self._watcher.stop()
        await self._sender.close()
        self._queue.close()
        logger.info("Agent stopped")

    # ── Poll cycle: watcher → parser → queue ────────────────────────────────

    async def _poll_loop(self) -> None:
        """Continuously poll watched files."""
        while self._running:
            try:
                await self._poll_cycle()
            except Exception:
                logger.exception("Poll cycle error")
            await asyncio.sleep(self._config.poll_interval)

    async def _poll_cycle(self) -> None:
        """Single poll iteration."""
        lines_by_path = self._watcher.poll()
        if not lines_by_path:
            return
        for path, lines in lines_by_path.items():
            await self._process_lines(path, lines)

    async def _process_lines(self, path: str, lines: list[str]) -> None:
        """Parse lines for a given path and enqueue results."""
        parser = self._parsers.get(path)
        if not parser:
            return
        for line in lines:
            parsed = parser.parse(line)
            if parsed is not None:
                self._queue.enqueue(parsed)

    # ── Send cycle: dequeue → sender ─────────────────────────────────────────

    async def _send_loop(self) -> None:
        """Continuously send batched events."""
        while self._running:
            try:
                await self._send_cycle()
            except Exception:
                logger.exception("Send cycle error")
            await asyncio.sleep(self._config.batch_interval)

    async def _send_cycle(self) -> None:
        """Single send iteration."""
        events = self._queue.dequeue(batch_size=self._config.batch_size)
        if not events:
            return

        event_data_list = [e["event_data"] for e in events]
        ids = [e["id"] for e in events]

        success = await self._sender.send_batch(event_data_list)
        if success:
            self._queue.mark_sent(ids)
        else:
            logger.warning("Failed to send %d event(s)", len(events))

    # ── Heartbeat cycle ──────────────────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """Periodically send heartbeats."""
        while self._running:
            try:
                await self._heartbeat_cycle()
            except Exception:
                logger.exception("Heartbeat error")
            await asyncio.sleep(self._config.heartbeat_interval)

    async def _heartbeat_cycle(self) -> None:
        """Send a single heartbeat."""
        ok = await self._sender.send_heartbeat()
        if not ok:
            logger.warning("Heartbeat failed")


def _setup_logging() -> None:
    """Configure structured logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _handle_signals(agent: Agent) -> None:
    """Set up signal handlers for graceful shutdown."""

    def _shutdown():
        asyncio.create_task(agent.stop())

    try:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _shutdown)
    except (NotImplementedError, AttributeError):
        # Signal handlers not available on all platforms (e.g. Windows)
        pass


async def main():
    """Entry point for ``python -m agent``."""
    import sys
    _setup_logging()

    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.toml"
    config = AgentConfig.from_toml(config_path)

    agent = Agent(config=config)
    _handle_signals(agent)

    try:
        await agent.run()
        # Keep running until stopped
        while agent._running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
