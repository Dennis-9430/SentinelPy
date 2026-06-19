"""Alert notifiers: console, file, webhook."""


class ConsoleNotifier:
    """Logs alerts to the console."""

    def send(self, alert: dict):
        """Print alert to stdout."""
        raise NotImplementedError("Fase 3: implementar notificador")
