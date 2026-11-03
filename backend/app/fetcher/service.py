"""Tiered fetch orchestration with cache."""

import asyncio
import dataclasses
import logging
from urllib.parse import urlsplit

from app.brand import SLUG
from app.cache.store import FetchCache
from app.config import Settings, get_settings
from app.fetcher.blocklist import check_supported_site
from app.fetcher.extract import extract_features
from app.fetcher.http_fetcher import http_fetch
from app.fetcher.models import (
    FetchedPage,
    FetchError,
    RawFetch,
    Tier,
    page_size_bytes,
)
from app.fetcher.playwright_fetcher import BrowserManager, playwright_fetch
from app.schemas import DataQuality
from app.security.url_guard import UrlBlockedError, validate_url

logger = logging.getLogger(f"{SLUG}.fetcher")

_BLOCKED_STATUSES = frozenset({401, 403, 429})
_DNS_MESSAGE = "The site address could not be resolved."

_shared_cache: FetchCache[FetchedPage] | None = None
_shared_browser: BrowserManager | None = None


def _as_fetch_error(exc: UrlBlockedError) -> FetchError:
    if isinstance(exc, FetchError):
        return exc
    return FetchError(exc.code, reason=exc.reason)


def _get_shared_cache(settings: Settings) -> FetchCache[FetchedPage]:
    global _shared_cache
    if _shared_cache is None:
        _shared_cache = FetchCache(
            ttl_seconds=settings.fetch_cache_ttl_seconds,
            max_total_bytes=settings.fetch_cache_max_mb * 1024 * 1024,
        )
    return _shared_cache


def _get_shared_browser() -> BrowserManager:
    global _shared_browser
    if _shared_browser is None:
        _shared_browser = BrowserManager()
    return _shared_browser


def prepare_fetch(
    url: str, *, settings: Settings, cache: FetchCache[FetchedPage]
) -> FetchedPage | str:
    """Run sync pre-checks. Returns a cached page or the normalized URL."""
    if settings.proxy_enabled:
        raise RuntimeError("proxy support is reserved for later and not available in v1")
    check_supported_site(url)
    try:
        normalized = validate_url(url)
    except UrlBlockedError as exc:
        if exc.code == "FETCH_FAILED":
            raise FetchError("FETCH_FAILED", _DNS_MESSAGE, reason=exc.reason) from exc
        raise _as_fetch_error(exc) from exc
    cached = cache.get(normalized)
    if cached is not None:
        return dataclasses.replace(cached, cached=True)
    return normalized


def classify_output(output: RawFetch, source_tier: Tier) -> tuple[Tier, DataQuality]:
    """Decide the tier label and data quality for a fetched response."""
    content_type = (output.content_type or "").lower()
    if content_type and "text/html" not in content_type and "application/xhtml" not in content_type:
        raise FetchError("NOT_HTML", reason=f"content-type: {output.content_type}")
    if not content_type and not output.html.lstrip().startswith("<"):
        raise FetchError("NOT_HTML", reason="body is not HTML")
    if output.status_code in _BLOCKED_STATUSES:
        if extract_features(output.html).has_og_data:
            return (3, "og_only")
        raise FetchError("FETCH_BLOCKED", reason=f"status: {output.status_code}")
    if output.status_code in (404, 410):
        # A missing page cannot be checked, but its template usually carries
        # the site's own meta tags, so salvage those before giving up.
        if extract_features(output.html).has_og_data:
            return (3, "og_only")
        raise FetchError("FETCH_FAILED", f"Page not found ({output.status_code}).")
    if 400 <= output.status_code < 600:
        raise FetchError("FETCH_FAILED", f"Site returned status {output.status_code}.")
    if source_tier == 1:
        return (1, "full")
    return (2, "partial")


def _finalize(
    request_url: str,
    output: RawFetch,
    tier: Tier,
    data_quality: DataQuality,
    cache: FetchCache[FetchedPage],
) -> FetchedPage:
    page = FetchedPage(
        request_url=request_url,
        final_url=output.final_url,
        status_code=output.status_code,
        html=output.html,
        headers=output.headers,
        screenshot=output.screenshot,
        tier=tier,
        data_quality=data_quality,
        features=extract_features(output.html),
    )
    cache.set(request_url, page, page_size_bytes(page))
    return page


async def fetch_page(
    url: str,
    *,
    settings: Settings | None = None,
    cache: FetchCache[FetchedPage] | None = None,
    browser_manager: BrowserManager | None = None,
) -> FetchedPage:
    """Fetch a page through tiers 1 to 3, using the cache when possible."""
    resolved = settings or get_settings()
    active_cache = cache if cache is not None else _get_shared_cache(resolved)
    prepared = await asyncio.to_thread(prepare_fetch, url, settings=resolved, cache=active_cache)
    if isinstance(prepared, FetchedPage):
        return prepared
    normalized = prepared
    host = urlsplit(normalized).hostname or "unknown"
    if resolved.use_playwright:
        try:
            manager = browser_manager or _get_shared_browser()
            output = await playwright_fetch(
                normalized,
                navigation_timeout_s=resolved.playwright_navigation_timeout_s,
                browser_manager=manager,
            )
            tier, quality = classify_output(output, 1)
        except FetchError as exc:
            if exc.code == "URL_BLOCKED":
                raise
            logger.info("tier 1 fell through", extra={"reason": exc.reason, "url_host": host})
        else:
            return _finalize(normalized, output, tier, quality, active_cache)
    try:
        output = await http_fetch(normalized)
    except UrlBlockedError as exc:
        raise _as_fetch_error(exc) from exc
    tier, quality = classify_output(output, 2)
    return _finalize(normalized, output, tier, quality, active_cache)
