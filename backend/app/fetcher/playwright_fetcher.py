"""Tier 1 fetch with headless Chromium."""

import asyncio
import logging
from typing import Any

from playwright.async_api import (
    Browser,
    Route,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from app.brand import SLUG
from app.fetcher.models import DESKTOP_UA, FetchError, RawFetch
from app.security.url_guard import MAX_RESPONSE_BYTES, UrlBlockedError, validate_url

logger = logging.getLogger(f"{SLUG}.fetcher")

NETWORK_IDLE_TIMEOUT_MS = 3000
_BLOCKED_RESOURCE_TYPES = frozenset({"image", "font", "media"})


class BrowserManager:
    """Own one Chromium browser; hand out single-use contexts."""

    def __init__(self) -> None:
        self._manager: Any = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    async def get_browser(self) -> Browser:
        """Launch the shared browser on first use, then reuse it."""
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                if self._manager is None:
                    self._manager = async_playwright()
                playwright = await self._manager.start()
                self._browser = await playwright.chromium.launch(headless=True)
            return self._browser

    async def aclose(self) -> None:
        """Close the browser and release Playwright. Safe to call twice."""
        async with self._lock:
            if self._browser is not None:
                await self._browser.close()
                self._browser = None
            if self._manager is not None:
                await self._manager.stop()
                self._manager = None


async def _guard_route(route: Route) -> None:
    """Block heavy subresources and SSRF risky requests on every hop."""
    request = route.request
    if request.resource_type in _BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return
    try:
        await asyncio.to_thread(validate_url, request.url)
    except UrlBlockedError:
        await route.abort()
        return
    await route.continue_()


async def playwright_fetch(
    url: str, *, navigation_timeout_s: float, browser_manager: BrowserManager
) -> RawFetch:
    """Render a page in a fresh context and capture HTML plus screenshot."""
    try:
        browser = await browser_manager.get_browser()
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=DESKTOP_UA,
            locale="en-US",
        )
    except PlaywrightError as exc:
        raise FetchError("FETCH_FAILED", reason="browser unavailable") from exc
    try:
        await context.route("**/*", _guard_route)
        page = await context.new_page()
        try:
            response = await page.goto(
                url, wait_until="load", timeout=int(navigation_timeout_s * 1000)
            )
        except PlaywrightTimeoutError as exc:
            raise FetchError("FETCH_TIMEOUT") from exc
        except PlaywrightError as exc:
            raise FetchError("FETCH_FAILED", reason="navigation failed") from exc
        if response is None:
            raise FetchError("FETCH_FAILED", reason="no navigation response")
        try:
            await page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            pass
        try:
            final_url = await asyncio.to_thread(validate_url, page.url)
        except UrlBlockedError as exc:
            raise FetchError(exc.code, reason=exc.reason) from exc
        html = await page.content()
        if len(html.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise FetchError("RESPONSE_TOO_LARGE")
        screenshot = await page.screenshot(type="png")
        return RawFetch(
            final_url=final_url,
            status_code=response.status,
            headers=dict(response.headers),
            html=html,
            content_type=response.headers.get("content-type", ""),
            screenshot=screenshot,
        )
    finally:
        await context.close()
