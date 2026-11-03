"""YouTube video page checks built only on public page data.

Title, description, and thumbnail come from meta tags, duration and
caption tracks from the embedded player data, and the transcript from
the public timed text endpoint when tracks exist. Every rule is a
plain checklist item; nothing here predicts views or virality.
"""

import html as html_lib
import json
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag

from app.brand import SLUG, USER_AGENT
from app.schemas import Evidence, EvidenceType, Issue, IssueCategory, Severity

logger = logging.getLogger(f"{SLUG}.youtube")

TranscriptStatus = Literal["retrieved", "none", "unknown"]

CHECKLIST_LIMITATION = "YouTube results are checklist based and not a performance forecast."
TRANSCRIPT_UNKNOWN_LIMITATION = "Transcript availability could not be verified."

_TITLE_MIN = 30
_TITLE_MAX = 100
_HOOK_MIN = 20
_CHAPTER_MIN_DURATION_S = 180
_CHAPTER_MIN_LINES = 3
_TRANSCRIPT_CAP = 4000
_TRACK_SCAN_CAP = 50000
_TRACK_RESPONSE_CAP = 1024 * 1024
_TRACK_TIMEOUT_S = 10.0
_YT_SUFFIX = " - YouTube"

_VIDEO_HOSTS = frozenset({"youtube.com", "youtu.be"})
_VIDEO_PATHS = ("/shorts/", "/embed/", "/live/")

_TIMESTAMP_RE = re.compile(r"^\s*(?:(\d+):)?([0-5]?\d):([0-5]\d)\b")
_LINK_RE = re.compile(r"https?://[^\s\"'<>]+")

# Phrases that count as a call to action in the description, matched
# case insensitively on word boundaries. A short fixed list keeps the
# check deterministic; it is a heuristic, not a reading of intent.
_CTA_PHRASES = (
    "subscribe",
    "comment",
    "link below",
    "links below",
    "in the description",
    "sign up",
    "book",
    "call",
    "download",
    "follow",
    "learn more",
    "get started",
    "watch next",
    "try",
)
_CTA_RES = tuple(
    re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE) for phrase in _CTA_PHRASES
)

_DURATION_RES = (
    (re.compile(r'"approxDurationMs":"(\d+)"'), 1000),
    (re.compile(r'"lengthSeconds":"(\d+)"'), 1),
)


@dataclass(frozen=True)
class CaptionTrack:
    """One caption track reference from the embedded player data."""

    language: str
    track_url: str
    auto_generated: bool


@dataclass(frozen=True)
class YoutubeData:
    """Public video data extracted from the watch page."""

    video_id: str | None
    title: str | None
    description: str | None
    thumbnail_url: str | None
    duration_s: int | None
    tracks: tuple[CaptionTrack, ...]
    transcript: str | None
    transcript_status: TranscriptStatus


@dataclass(frozen=True)
class YoutubeAnalysis:
    """Ranked YouTube issues plus the data behind them."""

    issues: list[Issue]
    data: YoutubeData


@dataclass
class _YtContext:
    data: YoutubeData
    hook: str
    cta_found: bool
    links: int
    chapter_marks: list[int]
    chapters_ok: bool


_CheckFn = Callable[[_YtContext], list[Issue]]


@dataclass(frozen=True)
class _Rule:
    id: str
    severity: Severity
    run: _CheckFn


def is_youtube_video_url(url: str) -> bool:
    """True for watch, shorts, embed, live, and youtu.be video URLs."""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return False
    host = (parts.hostname or "").lower().rstrip(".")
    if not any(host == base or host.endswith("." + base) for base in _VIDEO_HOSTS):
        return False
    if host == "youtu.be" or host.endswith(".youtu.be"):
        return bool(parts.path.strip("/"))
    if parts.path == "/watch":
        return "v" in parse_qs(parts.query)
    return parts.path.startswith(_VIDEO_PATHS)


def extract_video_id(final_url: str) -> str | None:
    """Pull the video id from a watch, shorts, embed, live, or youtu.be URL."""
    try:
        parts = urlsplit((final_url or "").strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    values = parse_qs(parts.query).get("v", [])
    if values and values[0].strip():
        return values[0].strip()
    segments = [segment for segment in parts.path.split("/") if segment]
    if not segments:
        return None
    if host == "youtu.be" or host.endswith(".youtu.be"):
        return segments[0]
    if segments[0] in ("shorts", "embed", "live") and len(segments) > 1:
        return segments[1]
    return None


def _meta_content(soup: BeautifulSoup, attr: str, key: str) -> str | None:
    tag = soup.find("meta", attrs={attr: key})
    if not isinstance(tag, Tag):
        return None
    content = tag.get("content")
    return content if isinstance(content, str) else None


def _clean_title(raw: str) -> str:
    text = " ".join(raw.split())
    if text.endswith(_YT_SUFFIX):
        return text[: -len(_YT_SUFFIX)]
    return text


def _extract_title(soup: BeautifulSoup) -> str | None:
    og_title = _meta_content(soup, "property", "og:title")
    if og_title is not None:
        return _clean_title(og_title)
    tag = soup.title
    if isinstance(tag, Tag):
        return _clean_title(tag.get_text())
    named = _meta_content(soup, "name", "title")
    if named is not None:
        return _clean_title(named)
    return None


def _extract_description(soup: BeautifulSoup) -> str | None:
    og_description = _meta_content(soup, "property", "og:description")
    if og_description is not None:
        return og_description.replace("\r\n", "\n").strip()
    named = _meta_content(soup, "name", "description")
    if named is not None:
        return named.replace("\r\n", "\n").strip()
    return None


def _extract_thumbnail(soup: BeautifulSoup) -> str | None:
    og_image = _meta_content(soup, "property", "og:image")
    if og_image is None or not og_image.strip():
        return None
    return og_image.strip()


def _extract_duration_s(html: str) -> int | None:
    for pattern, divisor in _DURATION_RES:
        match = pattern.search(html)
        if match:
            return int(match.group(1)) // divisor
    return None


def _json_array(html: str, key: str) -> str:
    """Slice the raw JSON array assigned to "key":[ ... ]."""
    marker = f'"{key}":['
    start = html.find(marker)
    if start < 0:
        return ""
    begin = start + len(marker) - 1
    depth = 0
    in_string = False
    escaped = False
    for pos in range(begin, min(len(html), begin + _TRACK_SCAN_CAP)):
        char = html[pos]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return html[begin : pos + 1]
    return ""


def _caption_tracks(html: str) -> tuple[CaptionTrack, ...]:
    raw = _json_array(html, "captionTracks")
    if not raw:
        return ()
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError:
        logger.info("caption tracks unparseable")
        return ()
    if not isinstance(entries, list):
        return ()
    tracks: list[CaptionTrack] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = entry.get("baseUrl")
        language = entry.get("languageCode")
        if not isinstance(url, str) or not url or not isinstance(language, str) or not language:
            continue
        tracks.append(
            CaptionTrack(
                language=language, track_url=url, auto_generated=entry.get("kind") == "asr"
            )
        )
    return tuple(tracks)


def _pick_track(tracks: tuple[CaptionTrack, ...]) -> CaptionTrack | None:
    """Prefer manual English, then auto English, then the first track."""
    english = [track for track in tracks if track.language.lower().startswith("en")]
    for track in english:
        if not track.auto_generated:
            return track
    if english:
        return english[0]
    return tracks[0] if tracks else None


def _track_allowed(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme != "https":
        return False
    host = (parts.hostname or "").lower().rstrip(".")
    return host == "youtube.com" or host.endswith(".youtube.com")


def fetch_transcript(track: CaptionTrack, client: httpx.Client) -> str | None:
    """Download one caption track as plain text, or None when unavailable."""
    if not _track_allowed(track.track_url):
        return None
    try:
        response = client.get(track.track_url)
        response.raise_for_status()
        if len(response.content) > _TRACK_RESPONSE_CAP:
            return None
        root = ET.fromstring(response.content)
    except (httpx.HTTPError, ET.ParseError) as exc:
        logger.info("transcript fetch failed", extra={"reason": type(exc).__name__})
        return None
    texts = [(element.text or "").strip() for element in root.iter("text")]
    joined = " ".join(html_lib.unescape(text) for text in texts if text)
    return " ".join(joined.split())[:_TRANSCRIPT_CAP]


def first_description_line(description: str) -> str:
    """First non-empty line of the description, stripped."""
    for line in description.replace("\r\n", "\n").split("\n"):
        if line.strip():
            return line.strip()
    return ""


def extract_cta_line(description: str) -> str:
    """First line containing a CTA phrase, or "" when none matches."""
    for line in description.replace("\r\n", "\n").split("\n"):
        if any(pattern.search(line) for pattern in _CTA_RES):
            return " ".join(line.split())[:120]
    return ""


def _has_cta(description: str) -> bool:
    return any(pattern.search(description) for pattern in _CTA_RES)


def _chapter_marks(description: str) -> list[int]:
    """Start offsets in seconds for every timestamped line."""
    marks: list[int] = []
    for line in description.replace("\r\n", "\n").split("\n"):
        match = _TIMESTAMP_RE.match(line)
        if match:
            hours = int(match.group(1) or 0)
            marks.append(hours * 3600 + int(match.group(2)) * 60 + int(match.group(3)))
    return marks


def _has_chapters(description: str) -> bool:
    """Chapters need 3 timestamped lines starting at 00:00."""
    marks = _chapter_marks(description)
    return len(marks) >= _CHAPTER_MIN_LINES and marks[0] == 0


def _link_count(description: str) -> int:
    return len(_LINK_RE.findall(description))


_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _issue(
    rule_id: str,
    severity: Severity,
    title: str,
    confidence: float,
    evidence_type: EvidenceType,
    evidence: str,
    why_it_matters: str,
    suggested_fix: str,
    category: IssueCategory = "content",
) -> Issue:
    return Issue(
        id=rule_id,
        category=category,
        title=title,
        severity=severity,
        confidence=confidence,
        evidence=Evidence(type=evidence_type, value=evidence),
        source=rule_id,
        why_it_matters=why_it_matters,
        suggested_fix=suggested_fix,
        impact_rank=1,
    )


def _check_title_missing(ctx: _YtContext) -> list[Issue]:
    """Flag when the page data has no video title tag at all."""
    if ctx.data.title is None:
        return [
            _issue(
                "youtube-title-missing",
                "high",
                "Video title could not be read",
                1.0,
                "selector",
                'meta[property="og:title"]',
                "Search and suggested feeds need a title to show the video.",
                "Check the video loads and a title is set in YouTube Studio.",
                "seo",
            )
        ]
    return []


def _check_title_empty(ctx: _YtContext) -> list[Issue]:
    """Flag when the video title tag exists but holds no text."""
    if ctx.data.title == "":
        return [
            _issue(
                "youtube-title-empty",
                "high",
                "Video title is empty",
                1.0,
                "selector",
                "title",
                "An empty title leaves search and feeds with nothing to show.",
                "Set a descriptive title in YouTube Studio.",
                "seo",
            )
        ]
    return []


def _check_title_length(ctx: _YtContext) -> list[Issue]:
    """Flag when the title is under 30 or over 100 characters."""
    title = ctx.data.title
    if not title:
        return []
    length = len(title)
    if _TITLE_MIN <= length <= _TITLE_MAX:
        return []
    return [
        _issue(
            "youtube-title-length",
            "low",
            f"Video title is {length} characters",
            0.95,
            "metric",
            f"{length} characters (recommended 30 to 100)",
            "Long titles get cut off in search and feeds; short ones may say too little.",
            "Rewrite the title to 30 to 100 characters with the topic up front.",
            "seo",
        )
    ]


def _check_description_missing(ctx: _YtContext) -> list[Issue]:
    """Flag when the page data has no video description tag at all."""
    if ctx.data.description is None:
        return [
            _issue(
                "youtube-description-missing",
                "medium",
                "Video description is missing",
                1.0,
                "selector",
                'meta[property="og:description"]',
                "Descriptions help search understand the video and give viewers links.",
                "Add a description in YouTube Studio: summary first, links below.",
            )
        ]
    return []


def _check_description_hook(ctx: _YtContext) -> list[Issue]:
    """Flag when the first description line is missing or under 20 characters."""
    if ctx.data.description is None:
        return []
    if len(ctx.hook) >= _HOOK_MIN:
        return []
    return [
        _issue(
            "youtube-description-hook",
            "low",
            "Description opens without a hook",
            0.7,
            "text",
            ctx.hook if ctx.hook else "(empty first line)",
            "Only the first line or two shows before the Show more cut.",
            "Open with one line that says what the viewer gets.",
        )
    ]


def _check_cta_missing(ctx: _YtContext) -> list[Issue]:
    """Flag when the description holds none of the CTA phrases."""
    if ctx.data.description is None or ctx.cta_found:
        return []
    return [
        _issue(
            "youtube-cta-missing",
            "low",
            "Description has no call to action",
            0.7,
            "metric",
            f"0 of {len(_CTA_PHRASES)} CTA phrases found",
            "Viewers who read the description are warm; a CTA gives the next step.",
            "Add one CTA line such as subscribe, comment, or a booking link.",
        )
    ]


def _check_links_missing(ctx: _YtContext) -> list[Issue]:
    """Flag when the description holds no http links."""
    if ctx.data.description is None or ctx.links > 0:
        return []
    return [
        _issue(
            "youtube-links-missing",
            "low",
            "Description has no links",
            0.9,
            "metric",
            "0 links found",
            "Links turn viewers into site visits, bookings, or subscribers.",
            "Add the business website or booking page URL to the description.",
        )
    ]


def _check_chapters_missing(ctx: _YtContext) -> list[Issue]:
    """Flag when a video of 3 minutes or more has no valid chapters."""
    if ctx.data.description is None or ctx.chapters_ok:
        return []
    duration = ctx.data.duration_s
    if duration is None or duration < _CHAPTER_MIN_DURATION_S:
        return []
    return [
        _issue(
            "youtube-chapters-missing",
            "low",
            "Long video has no chapters",
            0.9,
            "metric",
            f"{len(ctx.chapter_marks)} timestamped lines (need 3 starting at 00:00)",
            "Chapters let viewers jump ahead and can appear in search results.",
            "Add at least 3 timestamped lines starting at 00:00.",
        )
    ]


def _check_thumbnail_missing(ctx: _YtContext) -> list[Issue]:
    """Flag when the page data has no thumbnail image tag."""
    if ctx.data.thumbnail_url is None:
        return [
            _issue(
                "youtube-thumbnail-missing",
                "medium",
                "Video thumbnail could not be read",
                1.0,
                "selector",
                'meta[property="og:image"]',
                "Thumbnails drive clicks from search and suggested feeds.",
                "Set a custom thumbnail in YouTube Studio.",
            )
        ]
    return []


def _check_captions_missing(ctx: _YtContext) -> list[Issue]:
    """Flag when the player data lists no caption tracks."""
    if not ctx.data.tracks:
        return [
            _issue(
                "youtube-captions-missing",
                "low",
                "No caption tracks found",
                0.9,
                "metric",
                "0 caption tracks in page data",
                "Captions help deaf viewers and help search index the video.",
                "Upload captions or review the auto captions in YouTube Studio.",
                "accessibility",
            )
        ]
    return []


_CHECKS: tuple[_Rule, ...] = (
    _Rule("youtube-title-missing", "high", _check_title_missing),
    _Rule("youtube-title-empty", "high", _check_title_empty),
    _Rule("youtube-title-length", "low", _check_title_length),
    _Rule("youtube-description-missing", "medium", _check_description_missing),
    _Rule("youtube-description-hook", "low", _check_description_hook),
    _Rule("youtube-cta-missing", "low", _check_cta_missing),
    _Rule("youtube-links-missing", "low", _check_links_missing),
    _Rule("youtube-chapters-missing", "low", _check_chapters_missing),
    _Rule("youtube-thumbnail-missing", "medium", _check_thumbnail_missing),
    _Rule("youtube-captions-missing", "low", _check_captions_missing),
)


def _extract_data(
    soup: BeautifulSoup, html: str, final_url: str, client: httpx.Client
) -> YoutubeData:
    tracks = _caption_tracks(html)
    picked = _pick_track(tracks)
    transcript: str | None = None
    if picked is not None:
        transcript = fetch_transcript(picked, client)
    if transcript is not None:
        status: TranscriptStatus = "retrieved"
    elif not tracks:
        status = "none"
    else:
        status = "unknown"
    return YoutubeData(
        video_id=extract_video_id(final_url),
        title=_extract_title(soup),
        description=_extract_description(soup),
        thumbnail_url=_extract_thumbnail(soup),
        duration_s=_extract_duration_s(html),
        tracks=tracks,
        transcript=transcript,
        transcript_status=status,
    )


def analyze_youtube(
    html: str, final_url: str, *, transcript_client: httpx.Client | None = None
) -> YoutubeAnalysis:
    """Extract public video data, fetch the transcript, run every rule."""
    owned = transcript_client is None
    if transcript_client is not None:
        client = transcript_client
    else:
        client = httpx.Client(timeout=_TRACK_TIMEOUT_S, headers={"User-Agent": USER_AGENT})
    try:
        soup = BeautifulSoup(html or "", "html.parser")
        data = _extract_data(soup, html or "", final_url, client)
        description = data.description or ""
        ctx = _YtContext(
            data=data,
            hook=first_description_line(description),
            cta_found=_has_cta(description),
            links=_link_count(description),
            chapter_marks=_chapter_marks(description),
            chapters_ok=_has_chapters(description),
        )
        issues: list[Issue] = []
        for rule in _CHECKS:
            issues.extend(rule.run(ctx))
        issues.sort(key=lambda item: _SEVERITY_ORDER[item.severity])
        for rank, issue in enumerate(issues, start=1):
            issue.impact_rank = rank
        return YoutubeAnalysis(issues=issues, data=data)
    finally:
        if owned:
            client.close()
