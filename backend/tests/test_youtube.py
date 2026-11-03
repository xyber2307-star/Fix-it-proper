"""YouTube analyzer tests: extraction plus one passing and one failing case per rule."""

import httpx
import pytest

from app.analyzers.youtube import (
    CaptionTrack,
    YoutubeAnalysis,
    analyze_youtube,
    extract_cta_line,
    extract_video_id,
    fetch_transcript,
    first_description_line,
    is_youtube_video_url,
)

URL = "https://www.youtube.com/watch?v=abc123XYZ_-"
GOOD_TITLE = "How to fix a leaking tap in 10 minutes at home"
GOOD_DESC = (
    "Fix your leaking tap today with parts from any hardware store.\n"
    "Subscribe for weekly repair videos.\n"
    "Book a plumber at https://example.com/book\n"
    "00:00 Intro\n01:30 Tools\n04:00 Fix the washer"
)
THUMB = "https://i.ytimg.com/vi/abc123XYZ_-/hqdefault.jpg"
TRACK_URL = "https://www.youtube.com/api/timedtext?v=abc123XYZ_-&lang=en"
TRANSCRIPT_XML = (
    '<?xml version="1.0" encoding="utf-8" ?>'
    '<transcript><text start="0" dur="2">hello &amp; welcome</text>'
    '<text start="2" dur="2">to the repair shop</text></transcript>'
)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace('"', "&quot;").replace("\n", "&#10;")


def _track(lang: str = "en", kind: str = "", url: str = TRACK_URL) -> str:
    kind_part = f',"kind":"{kind}"' if kind else ""
    return (
        f'{{"baseUrl":"{url}","name":{{"runs":[{{"text":"English"}}]}},'
        f'"vssId":".en","languageCode":"{lang}"{kind_part}}}'
    )


def _player(
    duration_ms: str | None = "372000", length_s: str | None = "372", tracks: str = ""
) -> str:
    details = '"videoId":"abc123XYZ_-"'
    if length_s is not None:
        details += f',"lengthSeconds":"{length_s}"'
    duration_part = f',"approxDurationMs":"{duration_ms}"' if duration_ms is not None else ""
    return (
        "<script>var ytInitialPlayerResponse = {"
        f'"videoDetails":{{{details}}},'
        f'"captions":{{"playerCaptionsTracklistRenderer":{{"captionTracks":[{tracks}]}}}},'
        '"playabilityStatus":{"status":"OK"}' + duration_part + "};</script>"
    )


def _watch(
    *,
    title_tag: str | None = None,
    desc_tag: str | None = None,
    thumb_tag: str | None = None,
    doctitle: str = "",
    player: str | None = None,
) -> str:
    if title_tag is None:
        title_tag = f'<meta property="og:title" content="{GOOD_TITLE}">'
    if desc_tag is None:
        desc_tag = f'<meta property="og:description" content="{_esc(GOOD_DESC)}">'
    if thumb_tag is None:
        thumb_tag = f'<meta property="og:image" content="{THUMB}">'
    if player is None:
        player = _player(tracks=_track())
    head = "".join([title_tag, desc_tag, thumb_tag, doctitle])
    return f"<html><head>{head}</head><body>{player}</body></html>"


def _transcript_client(xml: str = TRANSCRIPT_XML, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=xml)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _analyze(html: str, url: str = URL, client: httpx.Client | None = None) -> YoutubeAnalysis:
    owned = client is None
    active = client if client is not None else _transcript_client()
    try:
        return analyze_youtube(html, url, transcript_client=active)
    finally:
        if owned:
            active.close()


def _ids(result: YoutubeAnalysis) -> list[str]:
    return [issue.id for issue in result.issues]


def _desc_tag(text: str) -> str:
    return f'<meta property="og:description" content="{_esc(text)}">'


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc123",
        "https://youtube.com/watch?v=abc123&t=10s",
        "https://m.youtube.com/watch?v=abc123",
        "https://youtu.be/abc123",
        "https://www.youtube.com/shorts/abc123",
        "https://www.youtube.com/embed/abc123",
        "https://www.youtube.com/live/abc123",
    ],
)
def test_detects_video_urls(url):
    assert is_youtube_video_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/",
        "https://www.youtube.com/playlist?list=abc",
        "https://www.youtube.com/channel/abc",
        "https://www.youtube.com/results?search_query=plumber",
        "https://www.youtube.com/watch",
        "https://youtu.be/",
        "https://example.com/watch?v=abc",
        "",
        "not a url",
    ],
)
def test_rejects_non_video_urls(url):
    assert is_youtube_video_url(url) is False


@pytest.mark.parametrize(
    ("url", "video_id"),
    [
        ("https://www.youtube.com/watch?v=abc123XYZ_-", "abc123XYZ_-"),
        ("https://youtu.be/xyz789", "xyz789"),
        ("https://www.youtube.com/shorts/qqq111", "qqq111"),
        ("https://www.youtube.com/embed/eee222", "eee222"),
        ("https://www.youtube.com/live/lll333", "lll333"),
        ("https://www.youtube.com/playlist?list=abc", None),
        ("not a url", None),
    ],
)
def test_extracts_video_id(url, video_id):
    assert extract_video_id(url) == video_id


def test_good_page_passes_every_rule():
    result = _analyze(_watch())
    assert result.issues == []
    assert result.data.video_id == "abc123XYZ_-"
    assert result.data.title == GOOD_TITLE
    assert result.data.thumbnail_url == THUMB
    assert result.data.duration_s == 372
    assert result.data.transcript_status == "retrieved"
    assert result.data.transcript == "hello & welcome to the repair shop"


def test_title_suffix_stripped_from_doctitle():
    html = _watch(title_tag="", doctitle="<title>Leak fix guide for renters - YouTube</title>")
    assert _analyze(html).data.title == "Leak fix guide for renters"


def test_title_missing_fails():
    assert "youtube-title-missing" in _ids(_analyze(_watch(title_tag="")))


def test_title_missing_passes():
    assert "youtube-title-missing" not in _ids(_analyze(_watch()))


def test_title_empty_fails():
    html = _watch(title_tag='<meta property="og:title" content="   ">')
    assert "youtube-title-empty" in _ids(_analyze(html))


def test_title_empty_passes():
    assert "youtube-title-empty" not in _ids(_analyze(_watch()))


@pytest.mark.parametrize("title", ["Hi there", "x" * 101])
def test_title_length_fails(title):
    html = _watch(title_tag=f'<meta property="og:title" content="{title}">')
    assert "youtube-title-length" in _ids(_analyze(html))


@pytest.mark.parametrize("title", ["x" * 30, "x" * 100])
def test_title_length_passes(title):
    html = _watch(title_tag=f'<meta property="og:title" content="{title}">')
    assert "youtube-title-length" not in _ids(_analyze(html))


def test_description_missing_fails():
    assert "youtube-description-missing" in _ids(_analyze(_watch(desc_tag="")))


def test_description_missing_passes():
    assert "youtube-description-missing" not in _ids(_analyze(_watch()))


def test_hook_fails_on_short_first_line():
    html = _watch(desc_tag=_desc_tag("Hi.\nSubscribe for more.\nhttps://example.com/"))
    assert "youtube-description-hook" in _ids(_analyze(html))


def test_hook_fails_on_empty_description():
    assert "youtube-description-hook" in _ids(_analyze(_watch(desc_tag=_desc_tag(""))))


def test_hook_passes():
    assert "youtube-description-hook" not in _ids(_analyze(_watch()))


def test_cta_missing_fails():
    desc = (
        "Fix your leaking tap today with parts from any hardware store.\n"
        "Parts list at https://example.com/parts\n"
        "00:00 Intro\n01:30 Tools\n04:00 Fix the washer"
    )
    assert "youtube-cta-missing" in _ids(_analyze(_watch(desc_tag=_desc_tag(desc))))


def test_cta_missing_passes():
    assert "youtube-cta-missing" not in _ids(_analyze(_watch()))


def test_links_missing_fails():
    desc = "Fix your leaking tap today with parts from any hardware store.\nSubscribe for more."
    assert "youtube-links-missing" in _ids(_analyze(_watch(desc_tag=_desc_tag(desc))))


def test_links_missing_passes():
    assert "youtube-links-missing" not in _ids(_analyze(_watch()))


def test_chapters_missing_fails_on_two_lines():
    desc = GOOD_DESC.replace("04:00 Fix the washer", "Thanks for watching")
    assert "youtube-chapters-missing" in _ids(_analyze(_watch(desc_tag=_desc_tag(desc))))


def test_chapters_missing_fails_when_not_starting_at_zero():
    desc = GOOD_DESC.replace("00:00 Intro", "00:05 Intro")
    assert "youtube-chapters-missing" in _ids(_analyze(_watch(desc_tag=_desc_tag(desc))))


def test_chapters_passes():
    assert "youtube-chapters-missing" not in _ids(_analyze(_watch()))


def test_chapters_skipped_for_short_videos():
    player = _player(duration_ms="90000", length_s="90", tracks=_track())
    desc = "Short clip.\nSubscribe.\nhttps://example.com/"
    html = _watch(desc_tag=_desc_tag(desc), player=player)
    assert "youtube-chapters-missing" not in _ids(_analyze(html))


def test_chapters_skipped_when_duration_unknown():
    player = _player(duration_ms=None, length_s=None, tracks=_track())
    desc = "No timestamps here.\nSubscribe.\nhttps://example.com/"
    html = _watch(desc_tag=_desc_tag(desc), player=player)
    assert "youtube-chapters-missing" not in _ids(_analyze(html))


def test_chapters_use_length_seconds_fallback():
    player = _player(duration_ms=None, length_s="600", tracks=_track())
    desc = "No timestamps here.\nSubscribe.\nhttps://example.com/"
    result = _analyze(_watch(desc_tag=_desc_tag(desc), player=player))
    assert result.data.duration_s == 600
    assert "youtube-chapters-missing" in _ids(result)


def test_hour_timestamps_count_as_chapters():
    desc = GOOD_DESC.replace("04:00 Fix the washer", "1:02:03 Deep fix")
    assert "youtube-chapters-missing" not in _ids(_analyze(_watch(desc_tag=_desc_tag(desc))))


def test_thumbnail_missing_fails():
    assert "youtube-thumbnail-missing" in _ids(_analyze(_watch(thumb_tag="")))


def test_thumbnail_missing_passes():
    assert "youtube-thumbnail-missing" not in _ids(_analyze(_watch()))


def test_captions_missing_fails():
    result = _analyze(_watch(player=_player(tracks="")))
    assert "youtube-captions-missing" in _ids(result)
    assert result.data.transcript_status == "none"
    assert result.data.transcript is None


def test_captions_missing_passes():
    assert "youtube-captions-missing" not in _ids(_analyze(_watch()))


def test_transcript_prefers_manual_over_auto():
    auto_url = "https://www.youtube.com/api/timedtext?v=x&name=auto"
    manual_url = "https://www.youtube.com/api/timedtext?v=x&name=manual"

    def handler(request: httpx.Request) -> httpx.Response:
        word = "manual track" if "manual" in str(request.url) else "auto track"
        return httpx.Response(200, text=f"<transcript><text>{word}</text></transcript>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        tracks = ",".join([_track("en", "asr", auto_url), _track("en", "", manual_url)])
        result = _analyze(_watch(player=_player(tracks=tracks)), client=client)
    finally:
        client.close()
    assert result.data.transcript == "manual track"


def test_transcript_failure_marks_status_unknown():
    result = _analyze(_watch(), client=_transcript_client(status=404))
    assert result.data.transcript_status == "unknown"
    assert result.data.transcript is None
    assert "youtube-captions-missing" not in _ids(result)


def test_transcript_bad_xml_marks_status_unknown():
    result = _analyze(_watch(), client=_transcript_client(xml="<not xml"))
    assert result.data.transcript_status == "unknown"


def test_transcript_unescapes_track_url():
    escaped = "https://www.youtube.com/api/timedtext?v=x\\u0026lang=en"
    result = _analyze(_watch(player=_player(tracks=_track(url=escaped))))
    assert result.data.transcript_status == "retrieved"


def test_transcript_rejects_off_domain_track():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not request off-domain tracks")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        track = CaptionTrack(
            language="en", track_url="https://evil.example/track", auto_generated=False
        )
        assert fetch_transcript(track, client) is None
    finally:
        client.close()


def test_transcript_rejects_oversized_body():
    big = "<transcript><text>" + "x" * (1024 * 1024 + 1) + "</text></transcript>"
    result = _analyze(_watch(), client=_transcript_client(xml=big))
    assert result.data.transcript_status == "unknown"


def test_first_description_line_skips_blanks():
    assert first_description_line("\n\n  Real hook here  \nmore") == "Real hook here"
    assert first_description_line("   \n  ") == ""


def test_extract_cta_line():
    assert extract_cta_line("Intro line.\nSubscribe for weekly videos!") == (
        "Subscribe for weekly videos!"
    )
    assert extract_cta_line("Nothing asking the viewer to do anything.") == ""
