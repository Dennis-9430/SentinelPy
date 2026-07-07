"""Tests unitarios para el rate limiter de endpoints de agentes.

Testea el RateLimiter directamente (sin pasar por FastAPI),
inyectando el agente como keyword argument para evitar
la resolución de Depends(require_agent).
"""

import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.ratelimit import RateLimiter


class _FakeAgent:
    """Agente simulado para tests — solo necesita id."""

    def __init__(self, id: int):
        self.id = id


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_agent(id: int = 1):
    """Crea un agente fake con el id dado."""
    return _FakeAgent(id=id)


# ── Tests básicos ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_requests_within_limit_pass():
    """Verifica que requests dentro del límite pasan sin error."""
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    agent = _make_agent(id=1)

    # Las primeras 3 llamadas deben pasar y devolver el agente
    result = await limiter(agent=agent)
    assert result is agent

    result = await limiter(agent=agent)
    assert result is agent

    result = await limiter(agent=agent)
    assert result is agent


@pytest.mark.asyncio
async def test_exceeding_limit_returns_429():
    """Verifica que exceder el límite levanta HTTP 429 con los campos esperados."""
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    agent = _make_agent(id=1)

    for _ in range(3):
        await limiter(agent=agent)

    with pytest.raises(HTTPException) as exc_info:
        await limiter(agent=agent)

    assert exc_info.value.status_code == 429
    detail = exc_info.value.detail
    assert "Demasiadas solicitudes" in detail["detail"]
    assert "retry_after" in detail
    assert isinstance(detail["retry_after"], int)


@pytest.mark.asyncio
async def test_different_agents_have_independent_counters():
    """Verifica que agentes distintos tienen contadores independientes."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    agent_a = _make_agent(id=1)
    agent_b = _make_agent(id=2)

    # agente_a agota su límite
    await limiter(agent=agent_a)
    await limiter(agent=agent_a)

    with pytest.raises(HTTPException):
        await limiter(agent=agent_a)

    # agente_b todavía puede hacer requests
    result = await limiter(agent=agent_b)
    assert result is agent_b

    result = await limiter(agent=agent_b)
    assert result is agent_b

    # agente_b también agota su límite
    with pytest.raises(HTTPException):
        await limiter(agent=agent_b)


# ── Tests con tiempo simulado ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_counter_resets_after_window():
    """Verifica que el contador se resetea después de que la ventana expira."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    agent = _make_agent(id=1)

    base_time = 1000.0

    with patch.object(time, "time", return_value=base_time):
        # La primera tanda llena el límite
        await limiter(agent=agent)
        await limiter(agent=agent)

        # Esta debe fallar — límite alcanzado
        with pytest.raises(HTTPException) as exc_info:
            await limiter(agent=agent)
        assert exc_info.value.status_code == 429

    # Avanzar el tiempo más allá de la ventana
    with patch.object(time, "time", return_value=base_time + 61):
        # Después de la ventana, las entradas antiguas se limpiaron
        result = await limiter(agent=agent)
        assert result is agent


@pytest.mark.asyncio
async def test_window_slides_properly():
    """Verifica que el sliding window funciona correctamente.

    Escenario:
      - max_requests=2, window=60s
      - Request 1 en t=0
      - Request 2 en t=30
      - Request 3 en t=30 → falla (2 en la ventana)
      - Request 3 en t=61 → pasa (solo request 2 está en la ventana)
    """
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    agent = _make_agent(id=1)

    times = iter([1000.0, 1030.0, 1030.0, 1061.0])

    def _mock_time():
        return next(times)

    with patch.object(time, "time", side_effect=_mock_time):
        # Request 1 en t=1000
        await limiter(agent=agent)

        # Request 2 en t=1030
        await limiter(agent=agent)

        # Request 3 en t=1030 — debe fallar, 2 requests en ventana
        with pytest.raises(HTTPException):
            await limiter(agent=agent)

        # Request 4 en t=1061 — window_start=1001, request 1 expiró
        # Solo request 2 (t=1030) está en ventana → pasa
        result = await limiter(agent=agent)
        assert result is agent


@pytest.mark.asyncio
async def test_cleans_up_stale_entries():
    """Verifica que las entradas vencidas se limpian durante la verificación."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    agent = _make_agent(id=1)

    base_time = 1000.0

    with patch.object(time, "time", return_value=base_time):
        await limiter(agent=agent)

    # Avanzar casi el tiempo completo de la ventana
    with patch.object(time, "time", return_value=base_time + 59):
        # Solo hay 1 entrada, debería pasar
        await limiter(agent=agent)

        # Ahora hay 2, la primera aún no expiró (1000 >= 1059-60=999)
        # Esta debe fallar
        with pytest.raises(HTTPException):
            await limiter(agent=agent)

    # Avanzar más allá de la ventana desde base_time
    with patch.object(time, "time", return_value=base_time + 61):
        # window_start = 1000 + 61 - 60 = 1001
        # Entrada en 1000 expiró, entrada en 1059 sigue vigente
        # La de 1000 se limpia, queda 1 entry → pasa
        result = await limiter(agent=agent)
        assert result is agent
