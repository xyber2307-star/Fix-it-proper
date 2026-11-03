"""FetchCache tests with an injected clock. No loop needed."""

from app.cache.store import FetchCache


def _cache(
    ttl_seconds: int = 100, max_total_bytes: int = 1000, max_entries: int = 10
) -> tuple[FetchCache[str], list[float]]:
    now = [1000.0]
    cache: FetchCache[str] = FetchCache(
        ttl_seconds=ttl_seconds,
        max_total_bytes=max_total_bytes,
        max_entries=max_entries,
        clock=lambda: now[0],
    )
    return cache, now


def test_set_and_get_hit_and_miss():
    cache, _ = _cache()
    assert cache.set("a", "page-a", 100) is True
    assert cache.get("a") == "page-a"
    assert cache.get("missing") is None
    assert cache.hits == 1
    assert cache.misses == 1
    assert cache.used_bytes == 100
    assert len(cache) == 1


def test_expired_entries_miss_and_free_bytes():
    cache, now = _cache()
    cache.set("a", "page-a", 100)
    now[0] += 101.0
    assert cache.get("a") is None
    assert cache.used_bytes == 0
    assert len(cache) == 0


def test_evicts_least_recently_used_when_over_bytes():
    cache, _ = _cache(max_total_bytes=100)
    cache.set("a", "page-a", 60)
    cache.set("b", "page-b", 60)
    assert cache.get("a") is None
    assert cache.get("b") == "page-b"
    assert cache.used_bytes == 60


def test_get_refreshes_recency():
    cache, _ = _cache(max_total_bytes=100)
    cache.set("a", "page-a", 40)
    cache.set("b", "page-b", 40)
    assert cache.get("a") == "page-a"
    cache.set("c", "page-c", 40)
    assert cache.get("a") == "page-a"
    assert cache.get("b") is None
    assert cache.get("c") == "page-c"


def test_oversize_single_entry_is_rejected():
    cache, _ = _cache(max_total_bytes=100)
    assert cache.set("big", "page", 101) is False
    assert len(cache) == 0


def test_max_entries_evicts_oldest():
    cache, _ = _cache(max_entries=2)
    cache.set("a", "page-a", 10)
    cache.set("b", "page-b", 10)
    cache.set("c", "page-c", 10)
    assert cache.get("a") is None
    assert len(cache) == 2


def test_overwrite_replaces_size():
    cache, _ = _cache()
    cache.set("a", "page-a", 60)
    cache.set("a", "page-a2", 10)
    assert cache.get("a") == "page-a2"
    assert cache.used_bytes == 10


def test_clear_resets_everything():
    cache, _ = _cache()
    cache.set("a", "page-a", 10)
    cache.get("a")
    cache.clear()
    assert len(cache) == 0
    assert cache.used_bytes == 0
    assert cache.hits == 0
    assert cache.misses == 0
