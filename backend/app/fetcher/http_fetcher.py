"""Tier 2 fetch with httpx and a standard browser user agent."""

import httpx

from app.fetcher.models import DESKTOP_UA, RawFetch
from app.security.url_guard import fetch_url_guarded


async def http_fetch(url: str, *, client: httpx.AsyncClient | None = None) -> RawFetch:
    """Fetch a page over plain HTTP with SSRF guarded redirects."""
    result = await fetch_url_guarded(url, user_agent=DESKTOP_UA, client=client)
    return RawFetch(
        final_url=result.final_url,
        status_code=result.status_code,
        headers=dict(result.headers),
        html=result.text,
        content_type=result.content_type,
        screenshot=None,
    )
