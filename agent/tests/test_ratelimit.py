"""Tests for agent.ratelimit — token bucket rate limiter."""

import time
from unittest.mock import patch

import pytest

from agent.ratelimit import TokenBucketRateLimiter


class TestTokenBucketRateLimiter:
    """Token bucket rate limiter behavior."""

    def test_init_positive_rate(self):
        rl = TokenBucketRateLimiter(rate=5.0)
        assert rl._rate == 5.0

    def test_init_zero_rate_raises(self):
        with pytest.raises(ValueError, match="rate must be positive"):
            TokenBucketRateLimiter(rate=0)

    def test_init_negative_rate_raises(self):
        with pytest.raises(ValueError, match="rate must be positive"):
            TokenBucketRateLimiter(rate=-1.0)

    def test_burst_capacity(self):
        rl = TokenBucketRateLimiter(rate=5.0)
        # Default burst = rate * 2 = 10
        assert rl._burst == 10

    def test_custom_burst(self):
        rl = TokenBucketRateLimiter(rate=5.0, burst=20)
        assert rl._burst == 20

    def test_allow_consumes_tokens(self):
        rl = TokenBucketRateLimiter(rate=5.0, burst=5)
        assert rl.allow() is True
        assert rl._tokens == 4.0

    def test_allow_fails_when_empty(self):
        rl = TokenBucketRateLimiter(rate=1.0, burst=1)
        assert rl.allow() is True  # consume the 1 token
        assert rl.allow() is False  # no more tokens

    def test_refill_over_time(self):
        rl = TokenBucketRateLimiter(rate=10.0, burst=10)
        # Consume all tokens
        for _ in range(10):
            assert rl.allow() is True
        assert rl.allow() is False

        # Simulate time passing (1 second = 10 tokens)
        with patch("agent.ratelimit.time.monotonic") as mock_time:
            mock_time.return_value = rl._last_refill + 1.0
            assert rl.allow() is True  # refilled 10 tokens

    def test_refill_capped_at_burst(self):
        rl = TokenBucketRateLimiter(rate=10.0, burst=5)
        # Tokens start at burst (5), wait 10 seconds would refill 100
        with patch("agent.ratelimit.time.monotonic") as mock_time:
            mock_time.return_value = rl._last_refill + 10.0
            assert rl.allow() is True
            assert rl._tokens == 4.0  # 5 - 1 consumed, capped at burst

    def test_allow_multiple_tokens(self):
        rl = TokenBucketRateLimiter(rate=10.0, burst=10)
        assert rl.allow(count=3) is True
        assert rl._tokens == 7.0

    def test_allow_multiple_fails_if_insufficient(self):
        rl = TokenBucketRateLimiter(rate=5.0, burst=5)
        assert rl.allow(count=3) is True
        assert rl.allow(count=3) is False  # only 2 left

    def test_drop_count(self):
        rl = TokenBucketRateLimiter(rate=5.0, burst=5)
        assert rl.drop_count(10) == 5  # burst=5, so 5 of 10 would be dropped
        rl.allow(count=4)  # consume 4, 1 left
        assert rl.drop_count(3) == 2  # 1 available, 2 of 3 would be dropped

    def test_available_property(self):
        rl = TokenBucketRateLimiter(rate=5.0, burst=5)
        assert rl.available == 5.0
        rl.allow()
        assert rl.available == 4.0

    def test_real_time_refill(self):
        """Test that tokens refill with actual wall clock (small sleep)."""
        rl = TokenBucketRateLimiter(rate=100.0, burst=1)
        assert rl.allow() is True
        assert rl.allow() is False
        time.sleep(0.02)  # 20ms at 100/s = ~2 tokens
        assert rl.allow() is True
