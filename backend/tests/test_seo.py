"""SEO analyzer tests: one passing and one failing case per rule."""

from pathlib import Path

import httpx
import pytest

from app.analyzers.seo import SeoAnalysis, analyze_seo

FIXTURES = Path(__file__).parent / "fixtures" / "fetcher"
URL = "https://example.com/"
GOOD_TITLE = "Plumbing repairs in Springfield open now"


def _client(robots: int = 200, sitemap: int = 200, explode: bool = False) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if explode:
            raise httpx.ConnectError("down")
        if request.url.path == "/robots.txt":
            return httpx.Response(robots)
        if request.url.path == "/sitemap.xml":
            return httpx.Response(sitemap)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _analyze(html: str, url: str = URL, robots: int = 200, sitemap: int = 200) -> SeoAnalysis:
    client = _client(robots, sitemap)
    try:
        return analyze_seo(html, url, http_client=client)
    finally:
        client.close()


def _ids(result: SeoAnalysis) -> list[str]:
    return [issue.id for issue in result.issues]


def _head(body: str) -> str:
    return f"<html><head>{body}</head><body></body></html>"


def test_title_missing_fails():
    result = _analyze("<html><head></head><body><h1>Hi</h1></body></html>")
    assert "seo-title-missing" in _ids(result)


def test_title_missing_passes():
    result = _analyze(_head(f"<title>{GOOD_TITLE}</title>"))
    assert "seo-title-missing" not in _ids(result)


def test_title_empty_fails():
    result = _analyze(_head("<title>   </title>"))
    assert "seo-title-empty" in _ids(result)


def test_title_empty_passes():
    result = _analyze(_head(f"<title>{GOOD_TITLE}</title>"))
    assert "seo-title-empty" not in _ids(result)


@pytest.mark.parametrize("title", ["Hi there", "x" * 61])
def test_title_length_fails(title):
    result = _analyze(_head(f"<title>{title}</title>"))
    assert "seo-title-length" in _ids(result)


@pytest.mark.parametrize("title", ["x" * 30, "x" * 60])
def test_title_length_passes(title):
    result = _analyze(_head(f"<title>{title}</title>"))
    assert "seo-title-length" not in _ids(result)


def test_title_duplicate_h1_fails():
    html = _head("<title>Same Day Plumber</title>").replace(
        "</body>", "<h1>Same Day Plumber</h1></body>"
    )
    assert "seo-title-duplicate-h1" in _ids(_analyze(html))


def test_title_duplicate_h1_passes():
    html = _head("<title>Same Day Plumber</title>").replace(
        "</body>", "<h1>Emergency Repairs</h1></body>"
    )
    assert "seo-title-duplicate-h1" not in _ids(_analyze(html))


def test_desc_missing_fails():
    assert "seo-meta-description-missing" in _ids(_analyze(_head("")))
    html = _head('<meta name="description" content="   ">')
    assert "seo-meta-description-missing" in _ids(_analyze(html))


def test_desc_missing_passes():
    html = _head(f'<meta name="description" content="{"x" * 100}">')
    assert "seo-meta-description-missing" not in _ids(_analyze(html))


@pytest.mark.parametrize("desc", ["Too short.", "x" * 161])
def test_desc_length_fails(desc):
    html = _head(f'<meta name="description" content="{desc}">')
    assert "seo-meta-description-length" in _ids(_analyze(html))


@pytest.mark.parametrize("desc", ["x" * 70, "x" * 160])
def test_desc_length_passes(desc):
    html = _head(f'<meta name="description" content="{desc}">')
    assert "seo-meta-description-length" not in _ids(_analyze(html))


def test_h1_missing_fails():
    assert "seo-h1-missing" in _ids(_analyze(_head("")))


def test_h1_missing_passes():
    html = _head("").replace("</body>", "<h1>Topic</h1></body>")
    assert "seo-h1-missing" not in _ids(_analyze(html))


def test_h1_multiple_fails():
    html = _head("").replace("</body>", "<h1>A</h1><h1>B</h1></body>")
    result = _analyze(html)
    assert "seo-h1-multiple" in _ids(result)
    assert "2 h1 tags" in result.issues[_ids(result).index("seo-h1-multiple")].evidence.value


def test_h1_multiple_passes():
    html = _head("").replace("</body>", "<h1>Only</h1></body>")
    assert "seo-h1-multiple" not in _ids(_analyze(html))


def test_heading_order_fails():
    html = _head("").replace("</body>", "<h1>A</h1><h3>Skipped</h3></body>")
    result = _analyze(html)
    assert "seo-heading-order" in _ids(result)
    assert "h1 to h3" in result.issues[_ids(result).index("seo-heading-order")].evidence.value


def test_heading_order_passes():
    html = _head("").replace("</body>", "<h1>A</h1><h2>B</h2><h3>C</h3></body>")
    assert "seo-heading-order" not in _ids(_analyze(html))
    lone = _head("").replace("</body>", "<h2>Only</h2></body>")
    assert "seo-heading-order" not in _ids(_analyze(lone))


def test_canonical_missing_fails():
    assert "seo-canonical-missing" in _ids(_analyze(_head("")))


def test_canonical_missing_passes():
    html = _head('<link rel="canonical" href="https://example.com/page">')
    assert "seo-canonical-missing" not in _ids(_analyze(html))


def test_canonical_host_fails():
    html = _head('<link rel="canonical" href="https://other.com/page">')
    assert "seo-canonical-host" in _ids(_analyze(html))


def test_canonical_host_passes():
    same = _head('<link rel="canonical" href="https://example.com/page">')
    assert "seo-canonical-host" not in _ids(_analyze(same))
    www = _head('<link rel="canonical" href="https://www.example.com/page">')
    assert "seo-canonical-host" not in _ids(_analyze(www))
    relative = _head('<link rel="canonical" href="/page">')
    assert "seo-canonical-host" not in _ids(_analyze(relative))


@pytest.mark.parametrize("content", ["index, noindex, follow", "NOINDEX"])
def test_robots_noindex_fails(content):
    html = _head(f'<meta name="robots" content="{content}">')
    assert "seo-robots-noindex" in _ids(_analyze(html))


def test_robots_noindex_passes():
    html = _head('<meta name="robots" content="index, follow">')
    assert "seo-robots-noindex" not in _ids(_analyze(html))
    assert "seo-robots-noindex" not in _ids(_analyze(_head("")))


def test_img_alt_fails():
    html = _head("").replace("</body>", '<img src="a.jpg"><img src="b.jpg"></body>')
    result = _analyze(html)
    assert "seo-img-alt" in _ids(result)
    evidence = result.issues[_ids(result).index("seo-img-alt")].evidence.value
    assert "2 images missing alt" in evidence
    assert "a.jpg" in evidence


def test_img_alt_passes():
    html = _head("").replace(
        "</body>", '<img src="a.jpg" alt=""><img src="b.jpg" alt="Van"></body>'
    )
    assert "seo-img-alt" not in _ids(_analyze(html))


def test_img_dims_fails():
    html = _head("").replace("</body>", '<img src="a.jpg" alt="x"></body>')
    assert "seo-img-dimensions" in _ids(_analyze(html))
    partial = _head("").replace("</body>", '<img src="a.jpg" alt="x" width="10"></body>')
    assert "seo-img-dimensions" in _ids(_analyze(partial))


def test_img_dims_passes():
    html = _head("").replace("</body>", '<img src="a.jpg" alt="x" width="10" height="10"></body>')
    assert "seo-img-dimensions" not in _ids(_analyze(html))


@pytest.mark.parametrize("name", ["title", "description", "image"])
def test_og_tags_fail(name):
    assert f"seo-og-{name}" in _ids(_analyze(_head("")))


@pytest.mark.parametrize(
    ("name", "content"),
    [("title", "Headline"), ("description", "Summary"), ("image", "https://x.test/i.png")],
)
def test_og_tags_pass(name, content):
    html = _head(f'<meta property="og:{name}" content="{content}">')
    assert f"seo-og-{name}" not in _ids(_analyze(html))


def test_og_empty_content_fails():
    html = _head('<meta property="og:title" content="  ">')
    assert "seo-og-title" in _ids(_analyze(html))


def test_twitter_card_fails():
    assert "seo-twitter-card" in _ids(_analyze(_head("")))


def test_twitter_card_passes():
    html = _head('<meta name="twitter:card" content="summary_large_image">')
    assert "seo-twitter-card" not in _ids(_analyze(html))


def test_viewport_fails():
    assert "seo-viewport" in _ids(_analyze(_head("")))


def test_viewport_passes():
    html = _head('<meta name="viewport" content="width=device-width, initial-scale=1">')
    assert "seo-viewport" not in _ids(_analyze(html))


def test_lang_fails():
    assert "seo-lang" in _ids(_analyze("<html><head></head><body></body></html>"))


def test_lang_passes():
    assert "seo-lang" not in _ids(_analyze('<html lang="en"><body></body></html>'))


def test_link_empty_text_fails():
    html = _head("").replace("</body>", '<a href="/x"></a><a href="/y">   </a></body>')
    result = _analyze(html)
    assert "seo-link-empty-text" in _ids(result)
    evidence = result.issues[_ids(result).index("seo-link-empty-text")].evidence.value
    assert "2 links with empty anchor text" in evidence


def test_link_empty_text_passes():
    text = _head("").replace("</body>", '<a href="/x">Menu</a></body>')
    assert "seo-link-empty-text" not in _ids(_analyze(text))
    labeled = _head("").replace("</body>", '<a href="/x" aria-label="Menu"></a></body>')
    assert "seo-link-empty-text" not in _ids(_analyze(labeled))
    image = _head("").replace("</body>", '<a href="/x"><img src="i.jpg" alt="Menu"></a></body>')
    assert "seo-link-empty-text" not in _ids(_analyze(image))


@pytest.mark.parametrize(
    "anchor",
    ["<a>text</a>", '<a href="">t</a>', '<a href="http://exa mple.com/x">t</a>'],
)
def test_link_bad_href_fails(anchor):
    html = _head("").replace("</body>", f"{anchor}</body>")
    assert "seo-link-bad-href" in _ids(_analyze(html))


@pytest.mark.parametrize(
    "href", ["/ok", "https://other.com/", "#frag", "https://example.com/a?b=1"]
)
def test_link_bad_href_passes(href):
    html = _head("").replace("</body>", f'<a href="{href}">t</a></body>')
    assert "seo-link-bad-href" not in _ids(_analyze(html))


def test_structured_missing_fails():
    assert "seo-structured-data-missing" in _ids(_analyze(_head("")))


def test_structured_missing_passes():
    block = '<script type="application/ld+json">{"@type": "LocalBusiness"}</script>'
    html = _head("").replace("</body>", f"{block}</body>")
    assert "seo-structured-data-missing" not in _ids(_analyze(html))


def test_jsonld_invalid_fails():
    block = '<script type="application/ld+json">not json {{{</script>'
    html = _head("").replace("</body>", f"{block}</body>")
    result = _analyze(html)
    assert "seo-jsonld-invalid" in _ids(result)
    evidence = result.issues[_ids(result).index("seo-jsonld-invalid")].evidence.value
    assert "1 JSON-LD blocks failed to parse" in evidence


def test_jsonld_invalid_passes():
    block = '<script type="application/ld+json">{"@type": "LocalBusiness"}</script>'
    html = _head("").replace("</body>", f"{block}</body>")
    assert "seo-jsonld-invalid" not in _ids(_analyze(html))


@pytest.mark.parametrize("status", [404, 410])
def test_robots_txt_fails(status):
    result = _analyze(_head(""), robots=status)
    assert "seo-robots-txt" in _ids(result)
    assert result.stats.robots_txt == "missing"


def test_robots_txt_passes():
    result = _analyze(_head(""), robots=200)
    assert "seo-robots-txt" not in _ids(result)
    assert result.stats.robots_txt == "present"


def test_robots_txt_unreachable_yields_unknown():
    client = _client(explode=True)
    try:
        result = analyze_seo(_head(""), URL, http_client=client)
    finally:
        client.close()
    assert "seo-robots-txt" not in _ids(result)
    assert result.stats.robots_txt == "unknown"


def test_robots_txt_off_host_redirect_yields_unknown():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(302, headers={"location": "http://evil.com/x"})
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    try:
        result = analyze_seo(_head(""), URL, http_client=client)
    finally:
        client.close()
    assert "seo-robots-txt" not in _ids(result)
    assert result.stats.robots_txt == "unknown"


@pytest.mark.parametrize("status", [404, 410])
def test_sitemap_fails(status):
    result = _analyze(_head(""), sitemap=status)
    assert "seo-sitemap" in _ids(result)
    assert result.stats.sitemap_xml == "missing"


def test_sitemap_passes():
    result = _analyze(_head(""), sitemap=200)
    assert "seo-sitemap" not in _ids(result)
    assert result.stats.sitemap_xml == "present"


def test_sitemap_unreachable_yields_unknown():
    client = _client(explode=True)
    try:
        result = analyze_seo(_head(""), URL, http_client=client)
    finally:
        client.close()
    assert "seo-sitemap" not in _ids(result)
    assert result.stats.sitemap_xml == "unknown"


def test_https_fails():
    result = _analyze(_head(""), url="http://example.com/")
    assert "seo-https" in _ids(result)


def test_https_passes():
    assert "seo-https" not in _ids(_analyze(_head("")))


def test_mixed_content_fails():
    html = _head("").replace(
        "</body>",
        '<img src="http://cdn.example/x.jpg"><script src="http://cdn.example/a.js">'
        "</script></body>",
    )
    result = _analyze(html)
    assert "seo-mixed-content" in _ids(result)
    evidence = result.issues[_ids(result).index("seo-mixed-content")].evidence.value
    assert "2 http subresources" in evidence


def test_mixed_content_srcset_fails():
    html = _head("").replace(
        "</body>", '<img srcset="http://cdn.example/a.jpg 1x, /b.jpg 2x"></body>'
    )
    assert "seo-mixed-content" in _ids(_analyze(html))


def test_mixed_content_passes():
    html = _head("").replace(
        "</body>",
        '<img src="https://cdn.example/x.jpg"><script src="/a.js"></script>'
        '<link rel="stylesheet" href="//cdn.example/x.css"></body>',
    )
    assert "seo-mixed-content" not in _ids(_analyze(html))
    plain = _head("").replace("</body>", '<img src="http://cdn.example/x.jpg"></body>')
    assert "seo-mixed-content" not in _ids(_analyze(plain, url="http://example.com/"))


def test_stats_counts_links_and_images():
    html = _head("").replace(
        "</body>",
        '<a href="/a">a</a><a href="https://example.com/b">b</a>'
        '<a href="https://other.com/">c</a><a href="mailto:x@y.z">d</a>'
        '<a href="#f">e</a><img src="a.jpg"><img src="b.jpg"></body>',
    )
    stats = _analyze(html).stats
    assert stats.internal_links == 3
    assert stats.external_links == 1
    assert stats.images == 2
    assert stats.robots_txt == "present"
    assert stats.sitemap_xml == "present"


def test_impact_rank_orders_severity():
    result = _analyze("<html><head></head><body><p>x</p></body></html>")
    severities = [issue.severity for issue in result.issues]
    assert severities == ["high"] * 4 + ["medium"] * 5 + ["low"] * 2
    assert [issue.impact_rank for issue in result.issues] == list(range(1, 12))
    assert result.issues[0].id == "seo-title-missing"


def test_full_page_fixture_reports_expected_rules():
    html = (FIXTURES / "full_page.html").read_text(encoding="utf-8")
    result = _analyze(html, url="https://plumbing.example/")
    ids = _ids(result)
    assert "seo-h1-multiple" in ids
    assert "seo-viewport" in ids
    assert "seo-jsonld-invalid" in ids
    assert "seo-title-missing" not in ids
    assert "seo-canonical-host" not in ids
    assert "seo-og-title" not in ids
    for issue in result.issues:
        assert 0 < issue.confidence <= 1
        assert issue.evidence.value


def test_no_performance_or_mobile_claims():
    html = (FIXTURES / "full_page.html").read_text(encoding="utf-8")
    results = [_analyze(html, url="https://plumbing.example/"), _analyze(_head(""))]
    for result in results:
        for issue in result.issues:
            assert issue.category != "performance"
            blob = (
                issue.title + issue.why_it_matters + issue.suggested_fix + issue.evidence.value
            ).lower()
            assert "performance" not in blob
            assert "mobile" not in blob


def test_empty_html_does_not_crash():
    result = _analyze("")
    assert "seo-title-missing" in _ids(result)
