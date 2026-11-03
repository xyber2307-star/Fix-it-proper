"""Tiny in-memory TTL cache with a total size cap."""

import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

_T = TypeVar("_T")


@dataclass
class _Entry(Generic[_T]):
    value: _T
    expires_at: float
    size_bytes: int


class FetchCache(Generic[_T]):
    """LRU-ish TTL cache bounded by total bytes and entry count."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 3600,
        max_total_bytes: int = 64 * 1024 * 1024,
        max_entries: int = 500,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_total_bytes = max_total_bytes
        self._max_entries = max_entries
        self._clock = clock
        self._items: OrderedDict[str, _Entry[_T]] = OrderedDict()
        self._used_bytes = 0
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> _T | None:
        """Return the cached value, or None on miss or expiry."""
        entry = self._items.get(key)
        if entry is None:
            self.misses += 1
            return None
        if entry.expires_at <= self._clock():
            del self._items[key]
            self._used_bytes -= entry.size_bytes
            self.misses += 1
            return None
        self._items.move_to_end(key)
        self.hits += 1
        return entry.value

    def set(self, key: str, value: _T, size_bytes: int) -> bool:
        """Store a value. False when the single entry exceeds the cap."""
        size_bytes = max(size_bytes, 0)
        if size_bytes > self._max_total_bytes:
            return False
        self._drop_expired()
        existing = self._items.pop(key, None)
        if existing is not None:
            self._used_bytes -= existing.size_bytes
        while self._items and (
            self._used_bytes + size_bytes > self._max_total_bytes
            or len(self._items) >= self._max_entries
        ):
            _, oldest = self._items.popitem(last=False)
            self._used_bytes -= oldest.size_bytes
        self._items[key] = _Entry(value, self._clock() + self._ttl_seconds, size_bytes)
        self._used_bytes += size_bytes
        return True

    def clear(self) -> None:
        """Remove every entry and reset counters."""
        self._items.clear()
        self._used_bytes = 0
        self.hits = 0
        self.misses = 0

    def _drop_expired(self) -> None:
        now = self._clock()
        expired = [key for key, entry in self._items.items() if entry.expires_at <= now]
        for key in expired:
            self._used_bytes -= self._items.pop(key).size_bytes

    @property
    def used_bytes(self) -> int:
        """Bytes currently held by live entries."""
        return self._used_bytes

    def __len__(self) -> int:
        return len(self._items)
