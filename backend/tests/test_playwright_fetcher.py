"""Tier 1 tests with fake Playwright objects. Needs a loop for asyncio.run."""

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.fetcher import playwright_fetcher as pw_module
from app.fetcher.models import FetchError
from app.fetcher.playwright_fetcher import _guard_route, playwright_fetch

PUBLIC_IP = "93.184.216.34"
_DEFAULT = object()


def _fake_browser_stack(
    *,
    page_url: str = "https://example.com/",
    html: str = "<p>hi</p>",
    status: int = 200,
    headers: dict[str, str] | None = None,
    response: Any = _DEFAULT,
    goto_side_effect: Any = None,
    browser_side_effect: Any = None,
) -> Any:
    if response is _DEFAULT:
        response = SimpleNamespace(status=status, headers=headers or {"content-type": "text/html"})
    page: Any = SimpleNamespace(url=page_url)
    if goto_side_effect is not None:
        page.goto = AsyncMock(side_effect=goto_side_effect)
    else:
        page.goto = AsyncMock(return_value=response)
    page.content = AsyncMock(return_value=html)
    page.screenshot = AsyncMock(return_value=b"fakepng")
    page.wait_for_load_state = AsyncMock()
    context: Any = SimpleNamespace()
    context.route = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    browser: Any = SimpleNamespace()
    browser.new_context = AsyncMock(return_value=context)
    manager: Any = SimpleNamespace()
    if browser_side_effect is not None:
        manager.get_browser = AsyncMock(side_effect=browser_side_effect)
    else:
        manager.get_browser = AsyncMock(return_value=browser)
    return SimpleNamespace(manager=manager, browser=browser, context=context, page=page)


def _fake_route(url: str, resource_type: str) -> Any:
    route: Any = SimpleNamespace()
    route.request = SimpleNamespace(url=url, resource_type=resource_type)
    route.abort = AsyncMock()
    route.continue_ = AsyncMock()
    return route


def test_success_captures_rendered_page(stub_dns, require_loop):
    stub_dns["example.com"] = [PUBLIC_IP]
    stack = _fake_browser_stack()
    raw = asyncio.run(
        playwright_fetch(
            "https://example.com/", navigation_timeout_s=15, browser_manager=stack.manager
        )
    )
    assert raw.final_url == "https://example.com/"
    assert raw.status_code == 200
    assert raw.html == "<p>hi</p>"
    assert raw.screenshot == b"fakepng"
    assert raw.headers["content-type"] == "text/html"
    context_kwargs = stack.browser.new_context.call_args.kwargs
    assert context_kwargs["viewport"] == {"width": 1280, "height": 800}
    assert "Chrome" in context_kwargs["user_agent"]
    goto_kwargs = stack.page.goto.call_args.kwargs
    assert goto_kwargs["wait_until"] == "load"
    assert goto_kwargs["timeout"] == 15000
    stack.context.close.assert_awaited_once()


def test_navigation_timeout_maps_to_fetch_timeout(stub_dns, require_loop):
    stub_dns["example.com"] = [PUBLIC_IP]
    stack = _fake_browser_stack(goto_side_effect=PlaywrightTimeoutError("slow"))
    with pytest.raises(FetchError) as exc_info:
        asyncio.run(
            playwright_fetch(
                "https://example.com/",
                navigation_timeout_s=15,
                browser_manager=stack.manager,
            )
        )
    assert exc_info.value.code == "FETCH_TIMEOUT"
    stack.context.close.assert_awaited_once()


def test_navigation_error_maps_to_fetch_failed(stub_dns, require_loop):
    stub_dns["example.com"] = [PUBLIC_IP]
    stack = _fake_browser_stack(goto_side_effect=PlaywrightError("boom"))
    with pytest.raises(FetchError) as exc_info:
        asyncio.run(
            playwright_fetch(
                "https://example.com/",
                navigation_timeout_s=15,
                browser_manager=stack.manager,
            )
        )
    assert exc_info.value.code == "FETCH_FAILED"
    stack.context.close.assert_awaited_once()


def test_missing_response_raises(stub_dns, require_loop):
    stub_dns["example.com"] = [PUBLIC_IP]
    stack = _fake_browser_stack(response=None)
    with pytest.raises(FetchError) as exc_info:
        asyncio.run(
            playwright_fetch(
                "https://example.com/",
                navigation_timeout_s=15,
                browser_manager=stack.manager,
            )
        )
    assert exc_info.value.code == "FETCH_FAILED"


def test_oversize_rendered_html_raises(monkeypatch, stub_dns, require_loop):
    stub_dns["example.com"] = [PUBLIC_IP]
    monkeypatch.setattr(pw_module, "MAX_RESPONSE_BYTES", 10)
    stack = _fake_browser_stack(html="x" * 20)
    with pytest.raises(FetchError) as exc_info:
        asyncio.run(
            playwright_fetch(
                "https://example.com/",
                navigation_timeout_s=15,
                browser_manager=stack.manager,
            )
        )
    assert exc_info.value.code == "RESPONSE_TOO_LARGE"


def test_browser_launch_failure_raises(require_loop):
    stack = _fake_browser_stack(browser_side_effect=PlaywrightError("no binary"))
    with pytest.raises(FetchError) as exc_info:
        asyncio.run(
            playwright_fetch(
                "https://example.com/",
                navigation_timeout_s=15,
                browser_manager=stack.manager,
            )
        )
    assert exc_info.value.code == "FETCH_FAILED"


def test_blocked_final_url_raises(require_loop):
    stack = _fake_browser_stack(page_url="http://127.0.0.1/x")
    with pytest.raises(FetchError) as exc_info:
        asyncio.run(
            playwright_fetch(
                "https://example.com/",
                navigation_timeout_s=15,
                browser_manager=stack.manager,
            )
        )
    assert exc_info.value.code == "URL_BLOCKED"


@pytest.mark.parametrize("resource_type", ["image", "font", "media"])
def test_guard_route_blocks_heavy_types(resource_type, require_loop):
    route = _fake_route("https://example.com/a.png", resource_type)
    asyncio.run(_guard_route(route))
    route.abort.assert_awaited_once()
    route.continue_.assert_not_awaited()


def test_guard_route_allows_safe_subresource(stub_dns, require_loop):
    stub_dns["example.com"] = [PUBLIC_IP]
    route = _fake_route("https://example.com/app.js", "script")
    asyncio.run(_guard_route(route))
    route.continue_.assert_awaited_once()
    route.abort.assert_not_awaited()


def test_guard_route_blocks_private_redirect_hop(require_loop):
    route = _fake_route("http://127.0.0.1/secret", "document")
    asyncio.run(_guard_route(route))
    route.abort.assert_awaited_once()
    route.continue_.assert_not_awaited()
