"""Extract page features from HTML with BeautifulSoup."""

import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from app.fetcher.models import PageFeatures

_MAX_H1 = 10
_PAGE_TEXT_LIMIT = 20000
_CTA_TEXT_LIMIT = 120
_CTA_VERBS = frozenset(
    {
        "get",
        "start",
        "try",
        "buy",
        "shop",
        "sign",
        "join",
        "book",
        "call",
        "contact",
        "request",
        "quote",
        "demo",
        "download",
        "subscribe",
        "order",
        "schedule",
        "apply",
    }
)


def _single_meta(soup: BeautifulSoup, attr: str, key: str) -> str | None:
    tag = soup.find("meta", attrs={attr: key})
    if isinstance(tag, Tag):
        content = tag.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return None


def _prefixed_meta(soup: BeautifulSoup, attr: str, prefix: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for tag in soup.find_all("meta", attrs={attr: True}):
        if not isinstance(tag, Tag):
            continue
        key = tag.get(attr)
        if not isinstance(key, str) or not key.startswith(prefix):
            continue
        content = tag.get("content")
        if isinstance(content, str) and content.strip():
            found[key[len(prefix) :]] = content.strip()
    return found


def _json_ld_blocks(soup: BeautifulSoup) -> list[Any]:
    blocks: list[Any] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not isinstance(tag, Tag):
            continue
        text = tag.string or ""
        if not text.strip():
            continue
        try:
            blocks.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    return blocks


def extract_features(html: str) -> PageFeatures:
    """Pull title, meta, OG, Twitter, JSON-LD, and H1s from HTML."""
    soup = BeautifulSoup(html or "", "html.parser")
    title_tag = soup.title
    title = title_tag.get_text(strip=True) or None if isinstance(title_tag, Tag) else None
    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical: str | None = None
    if isinstance(canonical_tag, Tag):
        href = canonical_tag.get("href")
        if isinstance(href, str) and href.strip():
            canonical = href.strip()
    html_tag = soup.find("html")
    lang: str | None = None
    if isinstance(html_tag, Tag):
        lang_attr = html_tag.get("lang")
        if isinstance(lang_attr, str) and lang_attr.strip():
            lang = lang_attr.strip()
    h1_texts = [
        heading.get_text(" ", strip=True)
        for heading in soup.find_all("h1")
        if isinstance(heading, Tag)
    ]
    return PageFeatures(
        title=title,
        meta_description=_single_meta(soup, "name", "description"),
        canonical=canonical,
        lang=lang,
        robots=_single_meta(soup, "name", "robots"),
        og=_prefixed_meta(soup, "property", "og:"),
        twitter=_prefixed_meta(soup, "name", "twitter:"),
        json_ld=_json_ld_blocks(soup),
        h1_texts=[text for text in h1_texts if text][:_MAX_H1],
    )


def extract_page_text(html: str) -> str:
    """Visible text without scripts or styles, capped for AI context."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())[:_PAGE_TEXT_LIMIT]


def extract_primary_cta(html: str) -> str:
    """First link or button text, preferring common call-to-action verbs."""
    soup = BeautifulSoup(html or "", "html.parser")
    candidates: list[str] = []
    for tag in soup.find_all(["a", "button"]):
        if not isinstance(tag, Tag):
            continue
        text = tag.get_text(" ", strip=True)
        if text and len(text) <= _CTA_TEXT_LIMIT:
            candidates.append(text)
    for text in candidates:
        words = set(re.findall(r"[a-z0-9]+", text.lower()))
        if words & _CTA_VERBS:
            return text
    return candidates[0] if candidates else ""
