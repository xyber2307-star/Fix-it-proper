"""Fetcher data shapes and fetch errors in contract form."""

import dataclasses
import json
from dataclasses import dataclass
from typing import Any, Literal

from app.schemas import DataQuality, ErrorResponse
from app.security.url_guard import UrlBlockedError

Tier = Literal[1, 2, 3]

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

PUBLIC_MESSAGES = {
    "URL_BLOCKED": "URL is not allowed for analysis.",
    "FETCH_FAILED": "Page could not be fetched.",
    "FETCH_TIMEOUT": "Fetching the page timed out.",
    "TOO_MANY_REDIRECTS": "URL redirected too many times.",
    "RESPONSE_TOO_LARGE": "Page is larger than 3 MB and was not fetched.",
    "NOT_HTML": "The URL did not return an HTML page.",
    "FETCH_BLOCKED": "The site blocked automated fetching.",
    "UNSUPPORTED_SITE": "Social media pages are not supported in v1.",
}

RETRYABLE_CODES = frozenset({"FETCH_TIMEOUT"})


class FetchError(UrlBlockedError):
    """A fetch failure with a human readable public message."""

    def __init__(self, code: str, public_message: str | None = None, reason: str = "") -> None:
        super().__init__(reason or code, code)
        self.public_message = public_message or PUBLIC_MESSAGES[code]

    @property
    def retryable(self) -> bool:
        """Only timeouts are worth retrying as-is."""
        return self.code in RETRYABLE_CODES

    def to_error_response(self) -> ErrorResponse:
        """Convert to the API contract error shape."""
        return ErrorResponse(code=self.code, message=self.public_message, retryable=self.retryable)


@dataclass(frozen=True)
class PageFeatures:
    """Debugging features extracted from fetched HTML."""

    title: str | None
    meta_description: str | None
    canonical: str | None
    lang: str | None
    robots: str | None
    og: dict[str, str]
    twitter: dict[str, str]
    json_ld: list[Any]
    h1_texts: list[str]

    @property
    def has_og_data(self) -> bool:
        """True when any salvageable meta tags were found."""
        return bool(self.og or self.twitter or self.json_ld)


@dataclass(frozen=True)
class RawFetch:
    """One tier attempt result before classification."""

    final_url: str
    status_code: int
    headers: dict[str, str]
    html: str
    content_type: str
    screenshot: bytes | None


@dataclass(frozen=True)
class FetchedPage:
    """Classified fetch result ready for analyzers and cache."""

    request_url: str
    final_url: str
    status_code: int
    html: str
    headers: dict[str, str]
    screenshot: bytes | None
    tier: Tier
    data_quality: DataQuality
    features: PageFeatures
    cached: bool = False


def page_size_bytes(page: FetchedPage) -> int:
    """Approximate stored size of a page for cache accounting."""
    features_json = json.dumps(dataclasses.asdict(page.features), default=str)
    headers_json = json.dumps(page.headers)
    return (
        len(page.html.encode("utf-8"))
        + len(page.screenshot or b"")
        + len(features_json.encode("utf-8"))
        + len(headers_json.encode("utf-8"))
        + 256
    )
