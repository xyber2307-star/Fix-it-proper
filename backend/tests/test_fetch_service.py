"""Fetcher service tests. Pre-checks run anywhere, tiers need a loop."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.cache.store import FetchCache
from app.config import Settings
from app.fetcher import service as service_module
from app.fetcher.models import (
    FetchedPage,
    FetchError,
    PageFeatures,
    RawFetch,
    Tier,
    page_size_bytes,
)
from app.fetcher.service import classify_output, fetch_page, prepare_fetch

PUBLIC_IP = "93.184.216.34"
FIXTURES = Path(__file__).parent / "fixtures" / "fetcher"


def _settings(**overrides: Any) -> Settings:
    return Settings(log_level="WARNING", **overrides)


def _cache() -> FetchCache[FetchedPage]:
    return FetchCache(ttl_seconds=3600, max_total_bytes=10_000_000)


def _features(**overrides: Any) -> PageFeatures:
    params: dict[str, Any] = {
        "title": None,
        "meta_description": None,
        "canonical": None,
        "lang": None,
        "robots": None,
        "og": {},
        "twitter": {},
        "json_ld": [],
        "h1_texts": [],
    }
    params.update(overrides)
    return PageFeatures(**params)


def _raw(**overrides: Any) -> RawFetch:
    params: dict[str, Any] = {
        "final_url": "https://example.com/",
        "status_code": 200,
        "headers": {"content-type": "text/html"},
        "html": "<html><head><title>T</title></head><body></body></html>",
        "content_type": "text/html",
        "screenshot": None,
    }
    params.update(overrides)
    return RawFetch(**params)


def _page(**overrides: Any) -> FetchedPage:
    params: dict[str, Any] = {
        "request_url": "https://example.com/",
        "final_url": "https://example.com/",
        "status_code": 200,
        "html": "<p>cached</p>",
        "headers": {"content-type": "text/html"},
        "screenshot": None,
        "tier": 2,
        "data_quality": "partial",
        "features": _features(),
    }
    params.update(overrides)
    return FetchedPage(**params)


def _read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_prepare_rejects_proxy_enabled():
    settings = _settings(proxy_enabled=True)
    with pytest.raises(RuntimeError, match="reserved for later"):
        prepare_fetch("https://example.com/", settings=settings, cache=_cache())


def test_prepare_rejects_blocked_domain_without_dns():
    with pytest.raises(FetchError) as exc_info:
        prepare_fetch("https://www.tiktok.com/@shop", settings=_settings(), cache=_cache())
    assert exc_info.value.code == "UNSUPPORTED_SITE"


def test_prepare_rejects_bad_url():
    with pytest.raises(FetchError) as exc_info:
        prepare_fetch("not-a-url", settings=_settings(), cache=_cache())
    assert exc_info.value.code == "URL_BLOCKED"


def test_prepare_maps_dns_failure(stub_dns: dict[str, list[str]]) -> None:
    with pytest.raises(FetchError) as exc_info:
        prepare_fetch("https://example.com/", settings=_settings(), cache=_cache())
    assert exc_info.value.code == "FETCH_FAILED"
    assert exc_info.value.public_message == "The site address could not be resolved."


def test_prepare_returns_normalized_url_on_cache_miss(
    stub_dns: dict[str, list[str]],
) -> None:
    stub_dns["example.com"] = [PUBLIC_IP]
    result = prepare_fetch("HTTPS://EXAMPLE.COM/page#frag", settings=_settings(), cache=_cache())
    assert result == "https://example.com/page"


def test_prepare_returns_cached_page(stub_dns: dict[str, list[str]]) -> None:
    stub_dns["example.com"] = [PUBLIC_IP]
    cache = _cache()
    page = _page()
    cache.set(page.request_url, page, page_size_bytes(page))
    result = prepare_fetch(page.request_url, settings=_settings(), cache=cache)
    assert isinstance(result, FetchedPage)
    assert result.cached is True
    assert cache.hits == 1


def test_classify_tier1_success_is_full():
    assert classify_output(_raw(), 1) == (1, "full")


def test_classify_tier2_success_is_partial():
    assert classify_output(_raw(), 2) == (2, "partial")


@pytest.mark.parametrize("tier", [1, 2])
def test_classify_blocked_status_with_og_is_og_only(tier: Tier) -> None:
    output = _raw(status_code=403, html=_read_fixture("blocked_403.html"))
    assert classify_output(output, tier) == (3, "og_only")


def test_classify_blocked_status_without_og_raises():
    output = _raw(status_code=429, html=_read_fixture("no_og_blocked.html"))
    with pytest.raises(FetchError) as exc_info:
        classify_output(output, 2)
    assert exc_info.value.code == "FETCH_BLOCKED"


def test_classify_non_html_raises():
    output = _raw(content_type="application/pdf", headers={"content-type": "application/pdf"})
    with pytest.raises(FetchError) as exc_info:
        classify_output(output, 2)
    assert exc_info.value.code == "NOT_HTML"


def test_classify_missing_content_type_sniffs_body():
    assert classify_output(_raw(content_type="", html="<p>hi</p>"), 2) == (2, "partial")
    with pytest.raises(FetchError) as exc_info:
        classify_output(_raw(content_type="", html="just text"), 2)
    assert exc_info.value.code == "NOT_HTML"


def test_classify_missing_pages_raise_not_found():
    with pytest.raises(FetchError) as exc_info:
        classify_output(_raw(status_code=404), 2)
    assert exc_info.value.code == "FETCH_FAILED"
    assert "404" in exc_info.value.public_message


def test_classify_server_errors_raise():
    with pytest.raises(FetchError) as exc_info:
        classify_output(_raw(status_code=500), 2)
    assert exc_info.value.code == "FETCH_FAILED"


@pytest.mark.parametrize(
    "code",
    [
        "URL_BLOCKED",
        "FETCH_FAILED",
        "FETCH_TIMEOUT",
        "TOO_MANY_REDIRECTS",
        "RESPONSE_TOO_LARGE",
        "NOT_HTML",
        "FETCH_BLOCKED",
        "UNSUPPORTED_SITE",
    ],
)
def test_fetch_error_converts_to_contract_shape(code: str) -> None:
    body = FetchError(code).to_error_response().model_dump()
    assert set(body.keys()) == {"code", "message", "retryable"}
    assert body["code"] == code
    assert body["retryable"] is (code == "FETCH_TIMEOUT")


def _patch_tiers(
    monkeypatch: pytest.MonkeyPatch,
    pw_result: RawFetch | Exception,
    http_result: RawFetch | Exception,
    calls: list[str],
) -> None:
    async def fake_pw(url: str, *, navigation_timeout_s: float, browser_manager: Any) -> RawFetch:
        calls.append("pw")
        if isinstance(pw_result, Exception):
            raise pw_result
        return pw_result

    async def fake_http(url: str, *, client: Any = None) -> RawFetch:
        calls.append("http")
        if isinstance(http_result, Exception):
            raise http_result
        return http_result

    monkeypatch.setattr(service_module, "playwright_fetch", fake_pw)
    monkeypatch.setattr(service_module, "http_fetch", fake_http)


def test_tier1_success_caches_page(monkeypatch, stub_dns, require_loop):
    stub_dns["example.com"] = [PUBLIC_IP]
    calls: list[str] = []
    raw = _raw(screenshot=b"fakepng")
    _patch_tiers(monkeypatch, raw, _raw(), calls)
    cache = _cache()
    settings = _settings()
    first = asyncio.run(fetch_page("https://example.com/", settings=settings, cache=cache))
    assert first.tier == 1
    assert first.data_quality == "full"
    assert first.screenshot == b"fakepng"
    assert first.cached is False
    second = asyncio.run(fetch_page("https://example.com/", settings=settings, cache=cache))
    assert second.cached is True
    assert calls == ["pw"]


def test_tier1_failure_falls_back_to_tier2(monkeypatch, stub_dns, require_loop):
    stub_dns["example.com"] = [PUBLIC_IP]
    calls: list[str] = []
    _patch_tiers(monkeypatch, FetchError("FETCH_TIMEOUT"), _raw(), calls)
    page = asyncio.run(fetch_page("https://example.com/", settings=_settings(), cache=_cache()))
    assert page.tier == 2
    assert page.data_quality == "partial"
    assert calls == ["pw", "http"]


def test_tier1_block_with_og_skips_tier2(monkeypatch, stub_dns, require_loop):
    stub_dns["example.com"] = [PUBLIC_IP]
    calls: list[str] = []
    blocked = _raw(status_code=403, html=_read_fixture("blocked_403.html"))
    _patch_tiers(monkeypatch, blocked, _raw(), calls)
    page = asyncio.run(fetch_page("https://example.com/", settings=_settings(), cache=_cache()))
    assert page.tier == 3
    assert page.data_quality == "og_only"
    assert calls == ["pw"]


def test_all_tiers_failing_raises_last_error(monkeypatch, stub_dns, require_loop):
    stub_dns["example.com"] = [PUBLIC_IP]
    calls: list[str] = []
    _patch_tiers(monkeypatch, FetchError("FETCH_TIMEOUT"), FetchError("FETCH_FAILED"), calls)
    with pytest.raises(FetchError) as exc_info:
        asyncio.run(fetch_page("https://example.com/", settings=_settings(), cache=_cache()))
    assert exc_info.value.code == "FETCH_FAILED"


def test_tier1_url_block_propagates_without_tier2(monkeypatch, stub_dns, require_loop):
    stub_dns["example.com"] = [PUBLIC_IP]
    calls: list[str] = []
    _patch_tiers(monkeypatch, FetchError("URL_BLOCKED"), _raw(), calls)
    with pytest.raises(FetchError) as exc_info:
        asyncio.run(fetch_page("https://example.com/", settings=_settings(), cache=_cache()))
    assert exc_info.value.code == "URL_BLOCKED"
    assert calls == ["pw"]


def test_playwright_disabled_uses_http_only(monkeypatch, stub_dns, require_loop):
    stub_dns["example.com"] = [PUBLIC_IP]
    calls: list[str] = []
    _patch_tiers(monkeypatch, _raw(), _raw(), calls)
    page = asyncio.run(
        fetch_page(
            "https://example.com/",
            settings=_settings(use_playwright=False),
            cache=_cache(),
        )
    )
    assert page.tier == 2
    assert calls == ["http"]


def test_fetch_page_rejects_proxy_enabled(stub_dns, require_loop):
    stub_dns["example.com"] = [PUBLIC_IP]
    with pytest.raises(RuntimeError, match="reserved for later"):
        asyncio.run(
            fetch_page(
                "https://example.com/",
                settings=_settings(proxy_enabled=True),
                cache=_cache(),
            )
        )
