"""Unit tests for the sliding window rate limiter. No loop needed."""

import time

import pytest

from app.security.rate_limit import RateLimiter, RateLimitExceeded


def test_allows_up_to_limit_then_raises():
    limiter = RateLimiter(limit=3)
    limiter.check("1.2.3.4")
    limiter.check("1.2.3.4")
    limiter.check("1.2.3.4")
    with pytest.raises(RateLimitExceeded) as exc_info:
        limiter.check("1.2.3.4")
    assert exc_info.value.retry_after_seconds >= 1


def test_keys_are_independent():
    limiter = RateLimiter(limit=1)
    limiter.check("1.1.1.1")
    limiter.check("2.2.2.2")
    with pytest.raises(RateLimitExceeded):
        limiter.check("1.1.1.1")


def test_window_slides_and_frees_quota(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    limiter = RateLimiter(limit=2, window_seconds=100)
    limiter.check("9.9.9.9")
    limiter.check("9.9.9.9")
    with pytest.raises(RateLimitExceeded):
        limiter.check("9.9.9.9")
    now[0] += 101.0
    limiter.check("9.9.9.9")


def test_reset_clears_all_hits():
    limiter = RateLimiter(limit=1)
    limiter.check("5.5.5.5")
    limiter.reset()
    limiter.check("5.5.5.5")
