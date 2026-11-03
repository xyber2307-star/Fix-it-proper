"""Blocklist tests. No loop needed."""

import pytest

from app.fetcher.blocklist import BLOCKED_DOMAINS, check_supported_site, host_is_blocked
from app.fetcher.models import FetchError


@pytest.mark.parametrize(
    "host",
    [
        "instagram.com",
        "www.facebook.com",
        "m.tiktok.com",
        "X.COM",
        "x.com.",
        "sub.domain.linkedin.com",
    ],
)
def test_blocked_hosts(host: str) -> None:
    assert host_is_blocked(host) is True


def test_messenger_subdomain_is_not_blocked():
    assert host_is_blocked("messenger.com") is False


@pytest.mark.parametrize(
    "host",
    [
        "example.com",
        "notfacebook.com",
        "facebook.com.evil.com",
        "myx.com",
        "tiktok.com.example.org",
        "",
    ],
)
def test_allowed_hosts(host: str) -> None:
    assert host_is_blocked(host) is False


def test_blocklist_covers_v1_out_of_scope_platforms():
    for domain in ("instagram.com", "facebook.com", "fb.com", "tiktok.com"):
        assert domain in BLOCKED_DOMAINS


def test_check_raises_unsupported_with_contract_shape():
    with pytest.raises(FetchError) as exc_info:
        check_supported_site("https://www.instagram.com/somepage")
    assert exc_info.value.code == "UNSUPPORTED_SITE"
    body = exc_info.value.to_error_response().model_dump()
    assert set(body.keys()) == {"code", "message", "retryable"}
    assert body["retryable"] is False


def test_check_passes_public_and_malformed_urls():
    check_supported_site("https://example.com/shop")
    check_supported_site("not a url at all")
