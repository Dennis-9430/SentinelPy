"""In-memory sliding window rate limiter for agent endpoints.

Uses a dict of agent_id -> deque[timestamp] for tracking.
Expired entries are cleaned up on every check.
Multi-process would require Redis, but for single-process
this implementation is sufficient.
"""

import time
from collections import deque

from fastapi import Depends, HTTPException, status

from app.auth import require_agent
from app.models.agent import Agent


class RateLimiter:
    """Configurable sliding window rate limiter.

    Args:
        max_requests: Maximum requests allowed in the window.
        window_seconds: Window duration in seconds.
    """

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = {}

    async def __call__(self, agent: Agent = Depends(require_agent)) -> Agent:
        """Check the rate limit for the authenticated agent.

        Args:
            agent: Authenticated agent (via require_agent).

        Returns:
            The same Agent instance if it does not exceed the limit.

        Raises:
            HTTPException 429: If the limit is exceeded.
        """
        agent_id = str(agent.id)
        now = time.time()
        window_start = now - self.window_seconds

        if agent_id not in self._buckets:
            self._buckets[agent_id] = deque()

        bucket = self._buckets[agent_id]

        # Remove expired entries
        while bucket and bucket[0] < window_start:
            bucket.popleft()

        # Check the limit
        if len(bucket) >= self.max_requests:
            oldest = bucket[0]
            retry_after = int(oldest + self.window_seconds - now) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "detail": (
                        f"Too many requests. "
                        f"Try again in {retry_after} seconds."
                    ),
                    "retry_after": retry_after,
                },
            )

        bucket.append(now)
        return agent
