"""Notifiers: send alerts to different channels.

When the correlation engine generates an alert, the notifier
delivers it to the configured channel.
"""

import logging

logger = logging.getLogger(__name__)

# Severity order for filtering (higher = more critical)
_SEVERITY_ORDER = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
}


class ConsoleNotifier:
    """Console notifier: shows alerts on stdout in a readable format.

    Useful for development and debugging. Shows the alert with colors
    (via logging levels) and structured formatting.
    """

    async def send(self, alerta: dict):
        """Send an alert to the console (async).

        Args:
            alerta: Dict with the alert data.
        """
        severidad = alerta.get("severity", "info").upper()
        titulo = alerta.get("title", "Untitled alert")
        descripcion = alerta.get("description", "")[:150]

        # Use different log levels depending on severity
        if alerta.get("severity") in ("critical", "high"):
            logger.warning("🔴 [%s] %s — %s", severidad, titulo, descripcion)
        elif alerta.get("severity") == "medium":
            logger.warning("🟡 [%s] %s — %s", severidad, titulo, descripcion)
        else:
            logger.info("🔵 [%s] %s — %s", severidad, titulo, descripcion)


class MultiNotifier:
    """Composite notifier: sends alerts to multiple channels.

    Allows registering several notifiers and sending the same alert
    to all of them (console, email, webhook, etc.).

    Each notifier can have a minimum severity level to avoid
    flooding channels with low-importance alerts.
    """

    def __init__(self):
        self._notificadores: list[tuple] = []

    def agregar(self, notificador, min_severity: str = "low"):
        """Add a notifier to the list with an optional severity filter.

        Args:
            notificador: Instance with async method send(alerta).
            min_severity: Minimum severity to send (default: "low").
                          Order: critical > high > medium > low > info.
        """
        self._notificadores.append((notificador, min_severity))

    async def send_all(self, alerta: dict):
        """Send an alert to all registered notifiers.

        Each notifier receives the alert only if its severity reaches
        the configured minimum. If a notifier fails, the
        rest continue.

        Args:
            alerta: Dict with the alert data.
        """
        severidad_alerta = alerta.get("severity", "info")
        nivel_alerta = _SEVERITY_ORDER.get(severidad_alerta, 0)

        for notificador, min_severity in self._notificadores:
            nivel_minimo = _SEVERITY_ORDER.get(min_severity, 0)
            if nivel_alerta < nivel_minimo:
                logger.debug(
                    "Skipping %s: severity %s < minimum %s",
                    type(notificador).__name__,
                    severidad_alerta,
                    min_severity,
                )
                continue
            try:
                await notificador.send(alerta)
            except Exception as e:
                logger.error(
                    "Error in notifier %s: %s",
                    type(notificador).__name__,
                    e,
                )
