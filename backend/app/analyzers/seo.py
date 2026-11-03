"""Pure SEO rules with no LLM calls.

Each check is a small function registered in _CHECKS with a stable rule
id and severity. Docstrings state the exact rule. Aggregate evidence
truncates each URL to 120 characters to bound issue size.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag

from app.brand import USER_AGENT
from app.schemas import Evidence, Issue, IssueCategory, Severity

Presence = Literal["present", "missing", "unknown"]

_EVIDENCE_URL_LIMIT = 120
_TITLE_MIN = 30
_TITLE_MAX = 60
_DESC_MIN = 70
_DESC_MAX = 160
_MAX_LISTED = 5

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class SeoStats:
    """Counts and crawl file states collected alongside issues."""

    internal_links: int
    external_links: int
    images: int
    robots_txt: Presence
    sitemap_xml: Presence


@dataclass(frozen=True)
class SeoAnalysis:
    """Ranked SEO issues plus supporting stats."""

    issues: list[Issue]
    stats: SeoStats


@dataclass
class _SeoContext:
    soup: BeautifulSoup
    final_url: str
    host: str
    robots_txt: Presence
    robots_evidence: str
    sitemap_xml: Presence
    sitemap_evidence: str


_CheckFn = Callable[[_SeoContext], list[Issue]]


@dataclass(frozen=True)
class _Rule:
    id: str
    severity: Severity
    run: _CheckFn


def _host_of(url: str) -> str:
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.").rstrip(".")


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _truncate(text: str, limit: int = _EVIDENCE_URL_LIMIT) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


def _title_text(soup: BeautifulSoup) -> str | None:
    tag = soup.title
    if not isinstance(tag, Tag):
        return None
    return tag.get_text(strip=True)


def _meta_content(soup: BeautifulSoup, attr: str, key: str) -> str | None:
    tag = soup.find("meta", attrs={attr: key})
    if not isinstance(tag, Tag):
        return None
    content = tag.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    return None


def _issue(
    rule_id: str,
    severity: Severity,
    title: str,
    confidence: float,
    evidence: str,
    why_it_matters: str,
    suggested_fix: str,
    category: IssueCategory = "seo",
) -> Issue:
    return Issue(
        id=rule_id,
        category=category,
        title=title,
        severity=severity,
        confidence=confidence,
        evidence=Evidence(type="text", value=evidence),
        source=rule_id,
        why_it_matters=why_it_matters,
        suggested_fix=suggested_fix,
        impact_rank=1,
    )


def _check_title_missing(ctx: _SeoContext) -> list[Issue]:
    """Flag when the HTML has no title tag at all."""
    if _title_text(ctx.soup) is None:
        return [
            _issue(
                "seo-title-missing",
                "high",
                "Page has no title tag",
                1.0,
                "no <title> tag in HTML",
                "Search results show the page URL or a blank title when the tag is missing.",
                "Add one <title> tag with the page topic and site name.",
            )
        ]
    return []


def _check_title_empty(ctx: _SeoContext) -> list[Issue]:
    """Flag when the title tag exists but holds no text."""
    title = _title_text(ctx.soup)
    if title is not None and not title:
        return [
            _issue(
                "seo-title-empty",
                "high",
                "Title tag is empty",
                1.0,
                "empty <title> tag",
                "An empty title gives search engines and tabs nothing to show.",
                "Write a title of 30 to 60 characters.",
            )
        ]
    return []


def _check_title_length(ctx: _SeoContext) -> list[Issue]:
    """Flag when the stripped title has under 30 or over 60 characters."""
    title = _title_text(ctx.soup)
    if title and (len(title) < _TITLE_MIN or len(title) > _TITLE_MAX):
        return [
            _issue(
                "seo-title-length",
                "low",
                "Title tag length is outside 30 to 60 characters",
                1.0,
                f"title is {len(title)} characters: {title}",
                "Short titles waste ranking space and long titles get cut off in results.",
                "Rewrite the title to 30 to 60 characters with the main keyword first.",
            )
        ]
    return []


def _check_title_duplicate_h1(ctx: _SeoContext) -> list[Issue]:
    """Flag when one H1 exists and matches the title after normalization."""
    title = _title_text(ctx.soup)
    h1s = [h.get_text(" ", strip=True) for h in ctx.soup.find_all("h1")]
    if title and len(h1s) == 1 and _norm(title) == _norm(h1s[0]):
        return [
            _issue(
                "seo-title-duplicate-h1",
                "low",
                "Title duplicates the H1",
                0.9,
                f"title matches h1: {title}",
                "Identical title and heading text wastes a chance to cover more search terms.",
                "Keep the H1 for readers and make the title tag distinct.",
            )
        ]
    return []


def _check_desc_missing(ctx: _SeoContext) -> list[Issue]:
    """Flag when the meta description tag is missing or empty."""
    if _meta_content(ctx.soup, "name", "description") is None:
        return [
            _issue(
                "seo-meta-description-missing",
                "high",
                "Page has no meta description",
                1.0,
                "no meta[name=description] tag with content",
                "Search engines invent the snippet, which usually lowers clicks.",
                "Add a meta description of 70 to 160 characters.",
            )
        ]
    return []


def _check_desc_length(ctx: _SeoContext) -> list[Issue]:
    """Flag when the meta description has under 70 or over 160 characters."""
    desc = _meta_content(ctx.soup, "name", "description")
    if desc is not None and (len(desc) < _DESC_MIN or len(desc) > _DESC_MAX):
        return [
            _issue(
                "seo-meta-description-length",
                "medium",
                "Meta description length is outside 70 to 160 characters",
                1.0,
                f"meta description is {len(desc)} characters: {desc}",
                "Short snippets say too little and long ones get cut off in results.",
                "Rewrite the description to 70 to 160 characters.",
            )
        ]
    return []


def _check_h1_missing(ctx: _SeoContext) -> list[Issue]:
    """Flag when the HTML has no h1 tag."""
    if not ctx.soup.find_all("h1"):
        return [
            _issue(
                "seo-h1-missing",
                "high",
                "Page has no H1",
                1.0,
                "no <h1> in HTML",
                "Visitors and search engines rely on the H1 to know what the page covers.",
                "Add one H1 that states the page topic.",
            )
        ]
    return []


def _check_h1_multiple(ctx: _SeoContext) -> list[Issue]:
    """Flag when the HTML has more than one h1 tag."""
    h1s = [h.get_text(" ", strip=True) for h in ctx.soup.find_all("h1")]
    if len(h1s) > 1:
        shown = " | ".join(_truncate(text, 80) for text in h1s[:3])
        return [
            _issue(
                "seo-h1-multiple",
                "medium",
                "Page has more than one H1",
                1.0,
                f"{len(h1s)} h1 tags found: {shown}",
                "Several H1 tags blur which heading defines the page topic.",
                "Keep one H1 and change the rest to H2.",
            )
        ]
    return []


def _check_heading_order(ctx: _SeoContext) -> list[Issue]:
    """Flag each heading more than one level deeper than the previous one."""
    issues: list[Issue] = []
    previous = 0
    for heading in ctx.soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        if not isinstance(heading, Tag):
            continue
        level = int(heading.name[1])
        if previous and level > previous + 1:
            text = _truncate(heading.get_text(" ", strip=True), 100)
            issues.append(
                _issue(
                    "seo-heading-order",
                    "low",
                    "Heading levels skip",
                    0.9,
                    f"heading jumps from h{previous} to h{level}: {text}",
                    "Skipped levels confuse screen reader users who navigate by headings.",
                    "Nest headings in order without skipping a level.",
                )
            )
        previous = level
    return issues


def _canonical_href(soup: BeautifulSoup) -> str | None:
    tag = soup.find("link", attrs={"rel": "canonical"})
    if not isinstance(tag, Tag):
        return None
    href = tag.get("href")
    if isinstance(href, str) and href.strip():
        return href.strip()
    return None


def _check_canonical_missing(ctx: _SeoContext) -> list[Issue]:
    """Flag when no link rel canonical tag with an href exists."""
    if _canonical_href(ctx.soup) is None:
        return [
            _issue(
                "seo-canonical-missing",
                "medium",
                "Page has no canonical tag",
                1.0,
                "no link[rel=canonical] tag with href",
                "Without a canonical tag, copies of this page can split ranking signals.",
                "Add link rel=canonical with the preferred page URL.",
            )
        ]
    return []


def _check_canonical_host(ctx: _SeoContext) -> list[Issue]:
    """Flag when the canonical href host differs from the page host."""
    href = _canonical_href(ctx.soup)
    if href is not None:
        target = _host_of(urljoin(ctx.final_url, href))
        if target and target != ctx.host:
            return [
                _issue(
                    "seo-canonical-host",
                    "medium",
                    "Canonical tag points to a different host",
                    0.95,
                    f"canonical points to {target}: {_truncate(href)}",
                    "A canonical to another host tells search engines to rank that host instead.",
                    "Point the canonical tag at this page host.",
                )
            ]
    return []


def _check_robots_noindex(ctx: _SeoContext) -> list[Issue]:
    """Flag when a robots meta tag lists noindex."""
    for tag in ctx.soup.find_all("meta", attrs={"name": True}):
        if not isinstance(tag, Tag):
            continue
        name = tag.get("name")
        content = tag.get("content")
        if not isinstance(name, str) or not isinstance(content, str):
            continue
        if name.strip().lower() != "robots":
            continue
        directives = [part.strip().lower() for part in content.split(",")]
        if "noindex" in directives:
            return [
                _issue(
                    "seo-robots-noindex",
                    "high",
                    "Robots meta blocks indexing",
                    1.0,
                    f"robots meta blocks indexing: {content.strip()}",
                    "A noindex tag keeps the page out of search results entirely.",
                    "Remove noindex from the robots meta tag if the page should rank.",
                )
            ]
    return []


def _img_src(img: Tag) -> str:
    src = img.get("src")
    if isinstance(src, str) and src.strip():
        return _truncate(src.strip())
    return "(no src)"


def _check_img_alt(ctx: _SeoContext) -> list[Issue]:
    """Flag images with no alt attribute. Empty alt counts as decorative."""
    missing = [img for img in ctx.soup.find_all("img") if not img.has_attr("alt")]
    if missing:
        shown = ", ".join(_img_src(img) for img in missing[:_MAX_LISTED])
        return [
            _issue(
                "seo-img-alt",
                "medium",
                "Images missing alt text",
                1.0,
                f"{len(missing)} images missing alt: {shown}",
                "Screen readers skip images without alt text and image search misses them.",
                "Add short descriptive alt text to each listed image.",
                category="accessibility",
            )
        ]
    return []


def _has_dims(img: Tag) -> bool:
    width = img.get("width")
    height = img.get("height")
    return (
        isinstance(width, str)
        and isinstance(height, str)
        and bool(width.strip())
        and bool(height.strip())
    )


def _check_img_dims(ctx: _SeoContext) -> list[Issue]:
    """Flag images missing a width or height attribute."""
    missing = [img for img in ctx.soup.find_all("img") if not _has_dims(img)]
    if missing:
        shown = ", ".join(_img_src(img) for img in missing[:_MAX_LISTED])
        return [
            _issue(
                "seo-img-dimensions",
                "low",
                "Images missing width and height",
                0.9,
                f"{len(missing)} images missing width or height: {shown}",
                "Images without set dimensions push page content around while loading.",
                "Add width and height attributes that match each image.",
                category="technical",
            )
        ]
    return []


def _check_og_tag(ctx: _SeoContext, name: str) -> list[Issue]:
    if _meta_content(ctx.soup, "property", f"og:{name}") is None:
        pretty = {"title": "title", "description": "description", "image": "image"}[name]
        fixes = {
            "title": "Add meta property og:title with the share headline.",
            "description": "Add meta property og:description with one summary sentence.",
            "image": "Add meta property og:image with an absolute image URL.",
        }
        whys = {
            "title": "Shares on social apps show a plain link without the OG title.",
            "description": "Shares on social apps show no summary without the OG description.",
            "image": "Shares on social apps show no preview image without the OG image.",
        }
        return [
            _issue(
                f"seo-og-{name}",
                "medium",
                f"Open Graph {pretty} missing",
                1.0,
                f"no meta[property=og:{name}] tag with content",
                whys[name],
                fixes[name],
            )
        ]
    return []


def _check_og_title(ctx: _SeoContext) -> list[Issue]:
    """Flag when the og:title tag is missing or empty."""
    return _check_og_tag(ctx, "title")


def _check_og_description(ctx: _SeoContext) -> list[Issue]:
    """Flag when the og:description tag is missing or empty."""
    return _check_og_tag(ctx, "description")


def _check_og_image(ctx: _SeoContext) -> list[Issue]:
    """Flag when the og:image tag is missing or empty."""
    return _check_og_tag(ctx, "image")


def _check_twitter_card(ctx: _SeoContext) -> list[Issue]:
    """Flag when the twitter:card tag is missing or empty."""
    if _meta_content(ctx.soup, "name", "twitter:card") is None:
        return [
            _issue(
                "seo-twitter-card",
                "low",
                "Twitter Card tag missing",
                1.0,
                "no meta[name=twitter:card] tag with content",
                "Posts on X show a plain link without card markup.",
                "Add meta name twitter:card, usually summary_large_image.",
            )
        ]
    return []


def _check_viewport(ctx: _SeoContext) -> list[Issue]:
    """Flag when the viewport meta tag is missing or empty."""
    if _meta_content(ctx.soup, "name", "viewport") is None:
        return [
            _issue(
                "seo-viewport",
                "high",
                "Viewport meta tag missing",
                1.0,
                "no meta[name=viewport] tag with content",
                "Browsers use the viewport tag to size the page on small screens.",
                "Add meta name=viewport with width=device-width, initial-scale=1.",
                category="technical",
            )
        ]
    return []


def _check_lang(ctx: _SeoContext) -> list[Issue]:
    """Flag when the html tag has no lang attribute."""
    html_tag = ctx.soup.find("html")
    lang: str | None = None
    if isinstance(html_tag, Tag):
        value = html_tag.get("lang")
        if isinstance(value, str) and value.strip():
            lang = value.strip()
    if lang is None:
        return [
            _issue(
                "seo-lang",
                "low",
                "Page has no lang attribute",
                1.0,
                "no lang attribute on <html>",
                "Screen readers guess pronunciation when the page language is missing.",
                "Add lang to the html tag, for example lang=en.",
                category="accessibility",
            )
        ]
    return []


def _link_href(link: Tag) -> str | None:
    href = link.get("href")
    if isinstance(href, str) and href.strip():
        return href.strip()
    return None


def _link_has_name(link: Tag) -> bool:
    if link.get_text(strip=True):
        return True
    label = link.get("aria-label")
    if isinstance(label, str) and label.strip():
        return True
    for img in link.find_all("img"):
        alt = img.get("alt")
        if isinstance(alt, str) and alt.strip():
            return True
    return False


def _check_link_empty_text(ctx: _SeoContext) -> list[Issue]:
    """Flag links with no text, aria-label, or image alt to name them."""
    bad = [link for link in ctx.soup.find_all("a") if not _link_has_name(link)]
    if bad:
        shown = ", ".join(_truncate(_link_href(link) or "(no href)") for link in bad[:_MAX_LISTED])
        return [
            _issue(
                "seo-link-empty-text",
                "low",
                "Links with empty anchor text",
                0.95,
                f"{len(bad)} links with empty anchor text: {shown}",
                "Links without text give readers and search engines no hint where they lead.",
                "Add descriptive text, an aria-label, or an image alt to each listed link.",
            )
        ]
    return []


def _href_is_broken(href: str | None) -> bool:
    if href is None or not href.strip():
        return True
    if any(char in href for char in (" ", "\t", "\n", "\r", "\x00")):
        return True
    try:
        urlsplit(href)
    except ValueError:
        return True
    return False


def _check_link_bad_href(ctx: _SeoContext) -> list[Issue]:
    """Flag links with missing or malformed href values by format only."""
    bad = [link for link in ctx.soup.find_all("a") if _href_is_broken(_link_href_raw(link))]
    if bad:
        shown = ", ".join(_truncate(_link_href(link) or "(no href)") for link in bad[:_MAX_LISTED])
        return [
            _issue(
                "seo-link-bad-href",
                "medium",
                "Links with malformed targets",
                0.9,
                f"{len(bad)} links with malformed targets: {shown}",
                "Malformed link targets confuse browsers and lead nowhere.",
                "Fix or remove each listed href.",
            )
        ]
    return []


def _link_href_raw(link: Tag) -> str | None:
    href = link.get("href")
    return href if isinstance(href, str) else None


def _json_ld_blocks(soup: BeautifulSoup) -> list[Tag]:
    blocks: list[Tag] = []
    for tag in soup.find_all("script"):
        if not isinstance(tag, Tag):
            continue
        script_type = tag.get("type")
        if isinstance(script_type, str) and script_type.strip().lower() == "application/ld+json":
            blocks.append(tag)
    return blocks


def _check_structured_missing(ctx: _SeoContext) -> list[Issue]:
    """Flag when the HTML has no JSON-LD script blocks."""
    if not _json_ld_blocks(ctx.soup):
        return [
            _issue(
                "seo-structured-data-missing",
                "medium",
                "No JSON-LD structured data",
                0.85,
                "no JSON-LD structured data found",
                "Search engines cannot build rich results without structured data.",
                "Add a JSON-LD script with the business or page schema.",
            )
        ]
    return []


def _check_jsonld_invalid(ctx: _SeoContext) -> list[Issue]:
    """Flag JSON-LD blocks whose text fails to parse as JSON."""
    errors: list[str] = []
    for tag in _json_ld_blocks(ctx.soup):
        text = tag.string or ""
        if not text.strip():
            continue
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
    if errors:
        return [
            _issue(
                "seo-jsonld-invalid",
                "medium",
                "JSON-LD block fails to parse",
                1.0,
                f"{len(errors)} JSON-LD blocks failed to parse: {_truncate(errors[0])}",
                "Broken JSON-LD is ignored, so the markup gives no benefit.",
                "Fix the JSON syntax in each listed block.",
            )
        ]
    return []


def _fetch_presence(client: httpx.Client, page_host: str, url: str) -> tuple[Presence, str]:
    """GET a crawl file once. Only a clean 404 or 410 counts as missing."""
    try:
        response = client.get(url)
    except httpx.HTTPError:
        return ("unknown", f"GET {url} could not be fetched")
    if _host_of(str(response.url)) != page_host:
        return ("unknown", f"GET {url} redirected off host")
    if 200 <= response.status_code < 300:
        return ("present", f"GET {url} returned {response.status_code}")
    if response.status_code in (404, 410):
        return ("missing", f"GET {url} returned {response.status_code}")
    return ("unknown", f"GET {url} returned {response.status_code}")


def _check_robots_txt(ctx: _SeoContext) -> list[Issue]:
    """Flag when GET /robots.txt returns 404 or 410."""
    if ctx.robots_txt == "missing":
        return [
            _issue(
                "seo-robots-txt",
                "low",
                "robots.txt not found",
                0.95,
                ctx.robots_evidence,
                "Crawlers look for robots.txt to learn crawl rules for the site.",
                "Publish a robots.txt at the site root, even a permissive one.",
            )
        ]
    return []


def _check_sitemap(ctx: _SeoContext) -> list[Issue]:
    """Flag when GET /sitemap.xml returns 404 or 410."""
    if ctx.sitemap_xml == "missing":
        return [
            _issue(
                "seo-sitemap",
                "low",
                "sitemap.xml not found",
                0.95,
                ctx.sitemap_evidence,
                "A sitemap helps crawlers find every page on the site.",
                "Publish a sitemap.xml at the site root and keep it updated.",
            )
        ]
    return []


def _check_https(ctx: _SeoContext) -> list[Issue]:
    """Flag when the final page URL does not use https."""
    try:
        scheme = urlsplit(ctx.final_url).scheme.lower()
    except ValueError:
        scheme = ""
    if scheme != "https":
        return [
            _issue(
                "seo-https",
                "high",
                "Page is not served over HTTPS",
                1.0,
                f"page served over http: {ctx.final_url}",
                "Browsers warn visitors on plain HTTP pages and some features stay disabled.",
                "Serve the whole site over HTTPS with a valid certificate.",
                category="technical",
            )
        ]
    return []


_MIXED_ATTRS: tuple[tuple[str, str], ...] = (
    ("img", "src"),
    ("img", "srcset"),
    ("script", "src"),
    ("link", "href"),
    ("source", "src"),
    ("source", "srcset"),
    ("video", "src"),
    ("video", "poster"),
    ("audio", "src"),
    ("iframe", "src"),
)


def _srcset_urls(value: str) -> list[str]:
    urls: list[str] = []
    for candidate in value.split(","):
        parts = candidate.strip().split()
        if parts:
            urls.append(parts[0])
    return urls


def _is_mixed_url(value: str) -> bool:
    try:
        return urlsplit(value.strip()).scheme.lower() == "http"
    except ValueError:
        return False


def _check_mixed_content(ctx: _SeoContext) -> list[Issue]:
    """Flag http subresources embedded in an https page."""
    try:
        page_secure = urlsplit(ctx.final_url).scheme.lower() == "https"
    except ValueError:
        return []
    if not page_secure:
        return []
    mixed: list[str] = []
    for tag_name, attr in _MIXED_ATTRS:
        for tag in ctx.soup.find_all(tag_name):
            if not isinstance(tag, Tag):
                continue
            value = tag.get(attr)
            if not isinstance(value, str) or not value.strip():
                continue
            candidates = _srcset_urls(value) if attr == "srcset" else [value.strip()]
            mixed.extend(url for url in candidates if _is_mixed_url(url))
    if mixed:
        shown = ", ".join(_truncate(url) for url in mixed[:_MAX_LISTED])
        return [
            _issue(
                "seo-mixed-content",
                "medium",
                "Page loads insecure subresources",
                0.95,
                f"{len(mixed)} http subresources on https page: {shown}",
                "HTTP files on an HTTPS page trigger browser warnings or get blocked.",
                "Serve each listed file over HTTPS.",
                category="technical",
            )
        ]
    return []


_CHECKS: tuple[_Rule, ...] = (
    _Rule("seo-title-missing", "high", _check_title_missing),
    _Rule("seo-title-empty", "high", _check_title_empty),
    _Rule("seo-title-length", "low", _check_title_length),
    _Rule("seo-title-duplicate-h1", "low", _check_title_duplicate_h1),
    _Rule("seo-meta-description-missing", "high", _check_desc_missing),
    _Rule("seo-meta-description-length", "medium", _check_desc_length),
    _Rule("seo-h1-missing", "high", _check_h1_missing),
    _Rule("seo-h1-multiple", "medium", _check_h1_multiple),
    _Rule("seo-heading-order", "low", _check_heading_order),
    _Rule("seo-canonical-missing", "medium", _check_canonical_missing),
    _Rule("seo-canonical-host", "medium", _check_canonical_host),
    _Rule("seo-robots-noindex", "high", _check_robots_noindex),
    _Rule("seo-img-alt", "medium", _check_img_alt),
    _Rule("seo-img-dimensions", "low", _check_img_dims),
    _Rule("seo-og-title", "medium", _check_og_title),
    _Rule("seo-og-description", "medium", _check_og_description),
    _Rule("seo-og-image", "medium", _check_og_image),
    _Rule("seo-twitter-card", "low", _check_twitter_card),
    _Rule("seo-viewport", "high", _check_viewport),
    _Rule("seo-lang", "low", _check_lang),
    _Rule("seo-link-empty-text", "low", _check_link_empty_text),
    _Rule("seo-link-bad-href", "medium", _check_link_bad_href),
    _Rule("seo-structured-data-missing", "medium", _check_structured_missing),
    _Rule("seo-jsonld-invalid", "medium", _check_jsonld_invalid),
    _Rule("seo-robots-txt", "low", _check_robots_txt),
    _Rule("seo-sitemap", "low", _check_sitemap),
    _Rule("seo-https", "high", _check_https),
    _Rule("seo-mixed-content", "medium", _check_mixed_content),
)


def _link_kind(page_host: str, final_url: str, href: str) -> str | None:
    """Classify a link as internal or external. None when not countable."""
    try:
        scheme = urlsplit(href).scheme.lower()
    except ValueError:
        return None
    if scheme and scheme not in ("http", "https"):
        return None
    if _host_of(urljoin(final_url, href)) == page_host:
        return "internal"
    return "external"


def _collect_stats(ctx: _SeoContext) -> SeoStats:
    internal = 0
    external = 0
    for link in ctx.soup.find_all("a"):
        if not isinstance(link, Tag):
            continue
        href = _link_href(link)
        if href is None:
            continue
        kind = _link_kind(ctx.host, ctx.final_url, href)
        if kind == "internal":
            internal += 1
        elif kind == "external":
            external += 1
    return SeoStats(
        internal_links=internal,
        external_links=external,
        images=len(ctx.soup.find_all("img")),
        robots_txt=ctx.robots_txt,
        sitemap_xml=ctx.sitemap_xml,
    )


def analyze_seo(
    html: str, final_url: str, *, http_client: httpx.Client | None = None
) -> SeoAnalysis:
    """Run every SEO rule over HTML and rank the issues found."""
    owned = http_client is None
    if http_client is not None:
        client = http_client
    else:
        client = httpx.Client(
            timeout=10.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
    try:
        soup = BeautifulSoup(html or "", "html.parser")
        host = _host_of(final_url)
        robots_txt, robots_evidence = _fetch_presence(
            client, host, urljoin(final_url, "/robots.txt")
        )
        sitemap_xml, sitemap_evidence = _fetch_presence(
            client, host, urljoin(final_url, "/sitemap.xml")
        )
        ctx = _SeoContext(
            soup=soup,
            final_url=final_url,
            host=host,
            robots_txt=robots_txt,
            robots_evidence=robots_evidence,
            sitemap_xml=sitemap_xml,
            sitemap_evidence=sitemap_evidence,
        )
        issues: list[Issue] = []
        for rule in _CHECKS:
            issues.extend(rule.run(ctx))
        issues.sort(key=lambda item: _SEVERITY_ORDER[item.severity])
        for rank, issue in enumerate(issues, start=1):
            issue.impact_rank = rank
        return SeoAnalysis(issues=issues, stats=_collect_stats(ctx))
    finally:
        if owned:
            client.close()
