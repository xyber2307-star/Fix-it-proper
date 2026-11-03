"""Tests for SSRF protection. All DNS is stubbed, no network is used."""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.security.url_guard import (
    MAX_REDIRECTS,
    MAX_RESPONSE_BYTES,
    TOTAL_TIMEOUT_SECONDS,
    UrlBlockedError,
    fetch_url_guarded,
    validate_url,
)
from tests.conftest import skip_without_loop

pytestmark = pytest.mark.usefixtures("stub_dns")


@pytest.fixture(autouse=True)
def _skip_async_fetch_tests_without_loop(request):
    if request.node.name.startswith("test_fetch_"):
        skip_without_loop()


PUBLIC_IP = "93.184.216.34"

BLOCKED_LITERAL_URLS = [
    "http://localhost/",
    "http://localhost:3000/admin",
    "http://LOCALHOST/",
    "http://localhost./",
    "http://app.localhost/",
    "http://127.0.0.1/",
    "http://127.1/",
    "http://127.0.1/",
    "http://2130706433/",
    "http://0x7f.0.0.1/",
    "http://0x7f000001/",
    "http://0177.0.0.1/",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
    "http://172.16.5.4/",
    "http://172.31.255.255/",
    "http://169.254.169.254/latest/meta-data/",
    "http://100.100.100.200/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://[fe80::1]/",
    "http://[fc00::1]/",
    "http://0.0.0.0/",
    "http://0/",
    "ftp://example.com/file",
    "file:///etc/passwd",
    "gopher://example.com/",
    "dict://example.com:2628/x",
    "javascript:alert(1)",
    "http://user:pass@example.com/",
    "http://example.com@127.0.0.1/",
    "not-a-url",
    "",
    "   ",
    "http:///missing-host",
    "http://",
    "https://",
    "http://exa mple.com/",
    "http://example.com:0/",
    "http://example.com:99999/",
]


@pytest.mark.parametrize("url", BLOCKED_LITERAL_URLS)
def test_validate_url_blocks_malicious_and_edge_cases(url, stub_dns):
    stub_dns["example.com"] = [PUBLIC_IP]
    with pytest.raises(UrlBlockedError):
        validate_url(url)


@pytest.mark.parametrize(
    "ips",
    [
        ["127.0.0.1"],
        ["10.1.2.3"],
        ["192.168.0.10"],
        ["169.254.169.254"],
        [PUBLIC_IP, "127.0.0.1"],
    ],
)
def test_validate_url_blocks_host_resolving_to_blocked_address(ips, stub_dns):
    stub_dns["evil.example"] = ips
    with pytest.raises(UrlBlockedError) as exc_info:
        validate_url("http://evil.example/")
    assert exc_info.value.code == "URL_BLOCKED"


def test_validate_url_blocks_unresolvable_host(stub_dns):
    with pytest.raises(UrlBlockedError) as exc_info:
        validate_url("http://does-not-exist.invalid/")
    assert exc_info.value.code == "FETCH_FAILED"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",
        "https://example.com:8443/shop?q=1",
        "HTTP://EXAMPLE.COM/Path",
        "https://shop.example.co.uk/",
    ],
)
def test_validate_url_allows_public_hosts(url, stub_dns):
    stub_dns["example.com"] = [PUBLIC_IP]
    stub_dns["shop.example.co.uk"] = [PUBLIC_IP]
    checked = validate_url(url)
    assert checked.startswith("http")
    assert " " not in checked


def test_validate_url_strips_fragment_and_lowercases(stub_dns):
    stub_dns["example.com"] = [PUBLIC_IP]
    assert validate_url("HTTP://EXAMPLE.COM/page#frag") == "http://example.com/page"


def test_limits_match_requirements():
    assert MAX_REDIRECTS == 5
    assert MAX_RESPONSE_BYTES == 3 * 1024 * 1024
    assert TOTAL_TIMEOUT_SECONDS == 25.0


def _mock_client(handler: Callable[..., Any]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_fetch_returns_body_for_public_url(stub_dns):
    stub_dns["shop.test"] = [PUBLIC_IP]

    def handler(request):
        return httpx.Response(
            200, headers={"content-type": "text/html; charset=utf-8"}, content=b"<p>hi</p>"
        )

    result = asyncio.run(
        fetch_url_guarded("http://shop.test/", client=_mock_client(handler), total_timeout=5.0)
    )
    assert result.status_code == 200
    assert result.text == "<p>hi</p>"
    assert result.redirect_count == 0
    assert result.final_url == "http://shop.test/"


def test_fetch_follows_relative_redirects(stub_dns):
    stub_dns["shop.test"] = [PUBLIC_IP]

    def handler(request):
        if request.url.path == "/a":
            return httpx.Response(302, headers={"location": "/b"})
        return httpx.Response(200, content=b"done")

    result = asyncio.run(
        fetch_url_guarded("http://shop.test/a", client=_mock_client(handler), total_timeout=5.0)
    )
    assert result.final_url == "http://shop.test/b"
    assert result.text == "done"
    assert result.redirect_count == 1


def test_fetch_blocks_redirect_to_private_ip(stub_dns):
    stub_dns["shop.test"] = [PUBLIC_IP]
    seen: list[str] = []

    def handler(request):
        seen.append(str(request.url))
        if len(seen) == 1:
            return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})
        return httpx.Response(200, content=b"must not reach here")

    with pytest.raises(UrlBlockedError) as exc_info:
        asyncio.run(
            fetch_url_guarded(
                "http://shop.test/go", client=_mock_client(handler), total_timeout=5.0
            )
        )
    assert exc_info.value.code == "URL_BLOCKED"
    assert seen == ["http://shop.test/go"]


def test_fetch_blocks_redirect_to_blocked_dns(stub_dns):
    stub_dns["shop.test"] = [PUBLIC_IP]
    stub_dns["evil.example"] = ["10.9.9.9"]

    def handler(request):
        return httpx.Response(302, headers={"location": "http://evil.example/"})

    with pytest.raises(UrlBlockedError) as exc_info:
        asyncio.run(
            fetch_url_guarded(
                "http://shop.test/go",
                client=_mock_client(handler),
                total_timeout=5.0,
                max_redirects=5,
            )
        )
    assert exc_info.value.code == "URL_BLOCKED"


def test_fetch_caps_redirect_chain(stub_dns):
    stub_dns["shop.test"] = [PUBLIC_IP]

    def handler(request):
        return httpx.Response(302, headers={"location": "/again"})

    with pytest.raises(UrlBlockedError) as exc_info:
        asyncio.run(
            fetch_url_guarded(
                "http://shop.test/start",
                client=_mock_client(handler),
                total_timeout=5.0,
                max_redirects=2,
            )
        )
    assert exc_info.value.code == "TOO_MANY_REDIRECTS"


def test_fetch_caps_response_size(stub_dns):
    stub_dns["shop.test"] = [PUBLIC_IP]

    def handler(request):
        return httpx.Response(200, content=b"x" * 2048)

    with pytest.raises(UrlBlockedError) as exc_info:
        asyncio.run(
            fetch_url_guarded("http://shop.test/big", client=_mock_client(handler), max_bytes=1024)
        )
    assert exc_info.value.code == "RESPONSE_TOO_LARGE"


def test_fetch_caps_total_time(stub_dns):
    stub_dns["shop.test"] = [PUBLIC_IP]

    async def handler(request):
        await asyncio.sleep(0.5)
        return httpx.Response(200, content=b"slow")

    with pytest.raises(UrlBlockedError) as exc_info:
        asyncio.run(
            fetch_url_guarded(
                "http://shop.test/slow", client=_mock_client(handler), total_timeout=0.05
            )
        )
    assert exc_info.value.code == "FETCH_TIMEOUT"


def test_fetch_maps_connection_errors(stub_dns):
    stub_dns["shop.test"] = [PUBLIC_IP]

    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(UrlBlockedError) as exc_info:
        asyncio.run(
            fetch_url_guarded("http://shop.test/", client=_mock_client(handler), total_timeout=5.0)
        )
    assert exc_info.value.code == "FETCH_FAILED"


def test_fetch_uses_custom_user_agent(stub_dns):
    stub_dns["shop.test"] = [PUBLIC_IP]
    seen: dict[str, str] = {}

    def handler(request):
        seen["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(
            200, headers={"content-type": "text/html", "x-extra": "1"}, content=b"ok"
        )

    result = asyncio.run(
        fetch_url_guarded(
            "http://shop.test/",
            user_agent="TestAgent/2.0",
            client=_mock_client(handler),
            total_timeout=5.0,
        )
    )
    assert seen["ua"] == "TestAgent/2.0"
    assert result.headers["x-extra"] == "1"
