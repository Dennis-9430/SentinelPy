"""Notificadores: envían alertas a distintos canales.

Cuando el motor de correlación genera una alerta, el notifier
se encarga de entregarla al canal configurado.
"""

import logging

logger = logging.getLogger(__name__)

# Orden de severidades para filtrar (mayor = más crítico)
_SEVERITY_ORDER = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
}


class ConsoleNotifier:
    """Notificador de consola: muestra alertas en stdout con formato legible.

    Útil para desarrollo y debugging. Muestra la alerta con colores
    (via logging levels) y formato estructurado.
    """

    async def send(self, alerta: dict):
        """Envía una alerta a la consola (async).

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

    Cada notificador puede tener un nivel mínimo de severidad para
    evitar saturar canales con alertas de baja importancia.
    """

    def __init__(self):
        self._notificadores: list[tuple] = []

    def agregar(self, notificador, min_severity: str = "low"):
        """Agrega un notificador a la lista con filtro de severidad opcional.

        Argumentos:
            notificador: Instancia con método async send(alerta).
            min_severity: Severidad mínima para enviar (default: "low").
                          Orden: critical > high > medium > low > info.
        """
        self._notificadores.append((notificador, min_severity))

    async def send_all(self, alerta: dict):
        """Envía una alerta a todos los notificadores registrados.

        Cada notificador recibe la alerta solo si la severidad de esta
        alcanza su mínimo configurado. Si un notificador falla, los
        demás continúan.

        Argumentos:
            alerta: Dict con los datos de la alerta.
        """
        severidad_alerta = alerta.get("severity", "info")
        nivel_alerta = _SEVERITY_ORDER.get(severidad_alerta, 0)

        for notificador, min_severity in self._notificadores:
            nivel_minimo = _SEVERITY_ORDER.get(min_severity, 0)
            if nivel_alerta < nivel_minimo:
                logger.debug(
                    "Saltando %s: severidad %s < mínimo %s",
                    type(notificador).__name__,
                    severidad_alerta,
                    min_severity,
                )
                continue
            try:
                await notificador.send(alerta)
            except Exception as e:
                logger.error(
                    "Error en notificador %s: %s",
                    type(notificador).__name__, e,
                )
