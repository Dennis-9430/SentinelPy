"""Log collectors: receive data from different sources.

Each collector implements start()/stop() and sends raw logs
to the pipeline for parsing and storage.
"""

import asyncio
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class SyslogUDPHandler(asyncio.DatagramProtocol):
    """UDP datagram handler for syslog.

    asyncio.DatagramProtocol receives UDP packets and passes them to the pipeline.
    One instance is created per call to create_datagram_endpoint().
    """

    def __init__(self, pipeline):
        """
        Args:
            pipeline: Pipeline instance that processes each message.
        """
        self.pipeline = pipeline

    def datagram_received(self, data: bytes, addr: tuple):
        """asyncio callback when a UDP datagram arrives.

        Decodes the message and sends it to the pipeline as an async task
        so the event loop is not blocked by processing.

        Args:
            data: Bytes of the received datagram.
            addr: (host, port) tuple of the sender.
        """
        # Decode assuming UTF-8, with a replace fallback for odd characters
        raw = data.decode("utf-8", errors="replace").strip()

        if raw:
            logger.debug("UDP received from %s: %s", addr, raw[:100])
            # Create an async task so we do not block the event loop
            asyncio.create_task(self.pipeline.process(raw, addr))


class SyslogCollector:
    """Syslog collector: listens for UDP messages.

    Listens on the configured port (default: 5140) and receives
    messages in RFC 3164 (BSD) format primarily.
    """

    def __init__(self, pipeline):
        """
        Args:
            pipeline: Pipeline that processes the received messages.
        """
        self.host = settings.syslog_host
        self.port = settings.syslog_port
        self.pipeline = pipeline
        self.transport = None
        self._server = None

    async def start(self):
        """Start the UDP server to receive syslog messages.

        Creates an async UDP endpoint on host:port.
        Each received datagram is handled by SyslogUDPHandler.
        """
        loop = asyncio.get_running_loop()

        logger.info("Starting syslog UDP collector on %s:%s", self.host, self.port)

        try:
            # Create the UDP socket and associate it with the handler
            self.transport, _ = await loop.create_datagram_endpoint(
                lambda: SyslogUDPHandler(self.pipeline),
                local_addr=(self.host, self.port),
            )
            logger.info("Syslog UDP collector started on port %s", self.port)
        except OSError as e:
            logger.error(
                "Could not start syslog collector on port %s: %s", self.port, e
            )
            raise

    async def stop(self):
        """Stop the syslog collector gracefully.

        Closes the UDP transport and waits for pending
        tasks to finish.
        """
        if self.transport:
            self.transport.close()
            logger.info("Syslog UDP collector stopped")


class FileCollector:
    """File collector: monitors log files in real time.

    TODO: Implement in a later phase. For now it is a placeholder.
    """

    async def watch(self, path: str):
        """Watch a file for new lines.

        Args:
            path: Path to the log file to monitor.

        Each new line is sent to the corresponding parser
        according to the extension or configuration.
        """
        raise NotImplementedError("Future phase: implement file watcher")
