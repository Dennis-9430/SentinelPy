"""Notificadores: envían alertas a distintos canales.

Cuando el motor de correlación genera una alerta, el notifier
se encarga de entregarla al canal configurado.
"""

import logging

logger = logging.getLogger(__name__)


class ConsoleNotifier:
    """Notificador de consola: muestra alertas en stdout con formato legible.

    Útil para desarrollo y debugging. Muestra la alerta con colores
    (via logging levels) y formato estructurado.
    """

    def send(self, alerta: dict):
        """Envía una alerta a la consola.

        Argumentos:
            alerta: Dict con los datos de la alerta.
        """
        severidad = alerta.get("severity", "info").upper()
        titulo = alerta.get("title", "Alerta sin título")
        descripcion = alerta.get("description", "")[:150]

        # Usar diferentes niveles de log según la severidad
        if alerta.get("severity") in ("critical", "high"):
            logger.warning("🔴 [%s] %s — %s", severidad, titulo, descripcion)
        elif alerta.get("severity") == "medium":
            logger.warning("🟡 [%s] %s — %s", severidad, titulo, descripcion)
        else:
            logger.info("🔵 [%s] %s — %s", severidad, titulo, descripcion)


class MultiNotifier:
    """Notificador compuesto: envía alertas a múltiples canales.

    Permite registrar varios notificadores y enviar la misma alerta
    a todos ellos (console, email, webhook, etc.).
    """

    def __init__(self):
        self._notificadores = []

    def agregar(self, notificador):
        """Agrega un notificador a la lista.

        Argumentos:
            notificador: Instancia con método send(alerta).
        """
        self._notificadores.append(notificador)

    def send_all(self, alerta: dict):
        """Envía una alerta a todos los notificadores registrados.

        Argumentos:
            alerta: Dict con los datos de la alerta.
        """
        for notificador in self._notificadores:
            try:
                notificador.send(alerta)
            except Exception as e:
                logger.error("Error en notificador %s: %s", type(notificador).__name__, e)
