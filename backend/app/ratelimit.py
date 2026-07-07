"""Rate limiter sliding window in-memory para endpoints de agentes.

Usa un dict de agent_id -> deque[timestamp] para tracking.
La limpieza de entradas vencidas ocurre en cada chequeo.
Para multi-proceso se necesitaría Redis, pero para single-process
esta implementación es suficiente.
"""

import time
from collections import deque

from fastapi import Depends, HTTPException, status

from app.auth import require_agent
from app.models.agent import Agent


class RateLimiter:
    """Rate limiter sliding window configurable.

    Args:
        max_requests: Máximo de requests permitidos en la ventana.
        window_seconds: Duración de la ventana en segundos.
    """

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = {}

    async def __call__(self, agent: Agent = Depends(require_agent)) -> Agent:
        """Verifica el rate limit para el agente autenticado.

        Args:
            agent: Agente autenticado (via require_agent).

        Returns:
            La misma instancia de Agent si no excede el límite.

        Raises:
            HTTPException 429: Si excede el límite.
        """
        agent_id = str(agent.id)
        now = time.time()
        window_start = now - self.window_seconds

        if agent_id not in self._buckets:
            self._buckets[agent_id] = deque()

        bucket = self._buckets[agent_id]

        # Limpiar entradas vencidas
        while bucket and bucket[0] < window_start:
            bucket.popleft()

        # Verificar límite
        if len(bucket) >= self.max_requests:
            oldest = bucket[0]
            retry_after = int(oldest + self.window_seconds - now) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "detail": (
                        f"Demasiadas solicitudes. "
                        f"Intente de nuevo en {retry_after} segundos."
                    ),
                    "retry_after": retry_after,
                },
            )

        bucket.append(now)
        return agent
