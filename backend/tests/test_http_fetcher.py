"""Tier 2 tests with mocked transport. Needs a loop."""

import asyncio

import httpx
import pytest

from app.fetcher.http_fetcher import http_fetch
from app.security.url_guard import UrlBlockedError

PUBLIC_IP = "93.184.216.34"


def test_http_fetch_maps_result_and_browser_ua(stub_dns, require_loop):
    stub_dns["shop.test"] = [PUBLIC_IP]
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<p>hi</p>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    raw = asyncio.run(http_fetch("http://shop.test/", client=client))
    assert raw.html == "<p>hi</p>"
    assert raw.status_code == 200
    assert raw.screenshot is None
    assert raw.headers["content-type"] == "text/html"
    assert seen["ua"].startswith("Mozilla/5.0")
    assert "Chrome" in seen["ua"]


def test_http_fetch_propagates_guard_errors(stub_dns, require_loop):
    stub_dns["shop.test"] = [PUBLIC_IP]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/loop"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(UrlBlockedError) as exc_info:
        asyncio.run(http_fetch("http://shop.test/", client=client))
    assert exc_info.value.code == "TOO_MANY_REDIRECTS"
