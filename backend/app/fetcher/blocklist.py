"""Domains that block bots and are out of scope for v1.

V1 covers public websites and landing pages only. The social platforms
below are login walled, aggressively block automated fetching, or forbid
it in their terms, so we refuse them with a clear error instead of
returning a hollow analysis of a block page.
"""

from urllib.parse import urlsplit

from app.fetcher.models import FetchError

BLOCKED_DOMAINS = (
    "instagram.com",
    "facebook.com",
    "fb.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "snapchat.com",
    "pinterest.com",
)


def host_is_blocked(host: str) -> bool:
    """True for a blocked domain or any of its subdomains."""
    cleaned = host.lower().rstrip(".")
    return any(cleaned == domain or cleaned.endswith("." + domain) for domain in BLOCKED_DOMAINS)


def check_supported_site(raw_url: str) -> None:
    """Raise FetchError when the URL targets a blocked domain.

    Malformed URLs pass through untouched; the SSRF guard reports them.
    """
    try:
        host = urlsplit((raw_url or "").strip()).hostname or ""
    except ValueError:
        return
    if host and host_is_blocked(host):
        raise FetchError("UNSUPPORTED_SITE", reason=f"blocked domain: {host}")
