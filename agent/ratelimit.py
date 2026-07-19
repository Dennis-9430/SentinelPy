"""Token bucket rate limiter for event ingestion.

Limits the number of events processed per second to prevent
overwhelming the server with high-frequency log sources.
"""

from __future__ import annotations

import time


class TokenBucketRateLimiter:
    """Token bucket rate limiter.

    Tokens are refilled at a constant rate up to the bucket capacity.
    Each event consumes one token. When the bucket is empty, events
    are dropped until tokens become available.

    Args:
        rate: Tokens per second (max events/sec).
        burst: Maximum tokens that can accumulate (burst capacity).
    """

    def __init__(self, rate: float, burst: int | None = None):
        if rate <= 0:
            raise ValueError("rate must be positive")
        self._rate = rate
        self._burst = burst or max(1, int(rate * 2))
        self._tokens = float(self._burst)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def allow(self, count: int = 1) -> bool:
        """Try to consume tokens.

        Args:
            count: Number of tokens to consume (default 1).

        Returns:
            True if tokens were available and consumed, False otherwise.
        """
        self._refill()
        if self._tokens >= count:
            self._tokens -= count
            return True
        return False

    def drop_count(self, count: int) -> int:
        """Return how many events from `count` would be dropped.

        Does NOT consume tokens — purely informational.
        """
        self._refill()
        allowed = min(count, int(self._tokens))
        return count - allowed

    @property
    def available(self) -> float:
        """Current available tokens (after refill)."""
        self._refill()
        return self._tokens
