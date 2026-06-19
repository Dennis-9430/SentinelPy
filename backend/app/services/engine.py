"""Motor de correlación: evalúa eventos contra reglas de detección.

El corazón de SentinelPy. Cada evento que ingresa se evalúa contra
todas las reglas activas. Si una regla matchea, se genera una alerta.
"""


class CorrelationEngine:
    """Motor de correlación de eventos.

    Mantiene una lista de reglas activas en memoria y evalúa
    cada evento entrante contra todas ellas.
    """

    async def evaluate(self, event: dict):
        """Evalúa un evento contra todas las reglas activas.

        Argumentos:
            event: Diccionario con el evento normalizado.

        Si alguna regla matchea, crea una alerta y la envía al notifier.
        TODO: implementar ventanas de correlación para reglas multi-evento.
        """
        raise NotImplementedError("Fase 3: implementar motor de correlación")
