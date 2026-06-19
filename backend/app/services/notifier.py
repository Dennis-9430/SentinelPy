"""Notificadores: envían alertas a distintos canales.

Cuando el motor de correlación genera una alerta, el notifier
se encarga de entregarla al canal configurado.
"""


class ConsoleNotifier:
    """Notificador de consola: muestra alertas en stdout.

    Útil para desarrollo y debugging. En producción se reemplaza
    por notificadores más sofisticados (email, webhook, Slack).
    """

    def send(self, alert: dict):
        """Envía una alerta a la consola.

        Argumentos:
            alert: Diccionario con los datos de la alerta.
        """
        raise NotImplementedError("Fase 3: implementar notificador")
