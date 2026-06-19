"""Correlation engine: matches events against detection rules."""


class CorrelationEngine:
    """Evaluates events against all active rules and generates alerts."""

    async def evaluate(self, event: dict):
        """Check an event against every active rule."""
        raise NotImplementedError("Fase 3: implementar motor de correlación")
