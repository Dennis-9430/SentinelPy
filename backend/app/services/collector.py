"""Log collectors: syslog, file, agent API."""


class SyslogCollector:
    """Listens for syslog messages (UDP/TCP)."""

    async def start(self):
        """Start listening for syslog messages."""
        raise NotImplementedError("Fase 1: implementar colector syslog")

    async def stop(self):
        """Gracefully stop the collector."""
        raise NotImplementedError


class FileCollector:
    """Watches log files for changes."""

    async def watch(self, path: str):
        """Watch a file for new lines."""
        raise NotImplementedError("Fase 1: implementar file watcher")
