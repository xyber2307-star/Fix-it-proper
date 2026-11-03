"""Per-key sliding window rate limiter kept in process memory."""

import time
from collections import deque

WINDOW_SECONDS = 3600


class RateLimitExceeded(Exception):
    """Raised when a key has used its quota inside the current window."""

    def __init__(self, retry_after_seconds: int, message: str | None = None) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after_seconds = max(retry_after_seconds, 1)
        self.message = message


class RateLimiter:
    """Count hits per key over a sliding window."""

    def __init__(
        self,
        limit: int,
        window_seconds: int = WINDOW_SECONDS,
        exceeded_message: str | None = None,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._exceeded_message = exceeded_message
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> None:
        """Record a hit for key, or raise RateLimitExceeded when over quota."""
        now = time.monotonic()
        cutoff = now - self._window
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self._limit:
            retry_after = int(hits[0] + self._window - now) + 1
            raise RateLimitExceeded(retry_after, self._exceeded_message)
        hits.append(now)
        if len(self._hits) > 10000:
            empty = [k for k, v in self._hits.items() if not v]
            for k in empty:
                del self._hits[k]

    def reset(self) -> None:
        """Clear all recorded hits. Used by tests for isolation."""
        self._hits.clear()
