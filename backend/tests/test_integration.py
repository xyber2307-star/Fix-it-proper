"""Integration tests for POST /api/analyze across the five contract cases."""

import dataclasses
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.service import AIResult
from app.analyzers.pagespeed import PageSpeedAnalysis
from app.analyzers.seo import SeoAnalysis, SeoStats
from app.analyzers.youtube import CHECKLIST_LIMITATION
from app.config import Settings
from app.fetcher.models import FetchedPage, FetchError, PageFeatures, Tier
from app.main import create_app
from app.schemas import AnalyzeResponse, DataQuality, ErrorResponse, Issue, Rewrite

HTML = (
    "<!doctype html><html lang='en'><head><title>Acme Plumbing Co</title></head>"
    "<body><h1>Austin Plumbers You Can Trust</h1>"
    "<a href='/quote'>Request a Free Quote</a></body></html>"
)
RESPONSE_KEYS = {
    "request_id",
    "url",
    "fetched_at",
    "data_quality",
    "summary",
    "issues",
    "rewrites",
    "limitations",
    "score",
}


@pytest.fixture
def client(require_loop):
    settings = Settings(
        frontend_origin="https://app.test", rate_limit_per_hour=100, log_level="WARNING"
    )
    return TestClient(create_app(settings))


def _page(html: str, *, quality: DataQuality = "full", tier: Tier = 1) -> FetchedPage:
    return FetchedPage(
        request_url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        html=html,
        headers={"content-type": "text/html"},
        screenshot=None,
        tier=tier,
        data_quality=quality,
        features=PageFeatures(
            title="Acme Plumbing Co",
            meta_description="Family plumbers in Austin for 20 years.",
            canonical="https://example.com/",
            lang="en",
            robots=None,
            og={"og:title": "Acme Plumbing Co"},
            twitter={},
            json_ld=[],
            h1_texts=["Austin Plumbers You Can Trust"],
        ),
    )


def _stats() -> SeoStats:
    return SeoStats(
        internal_links=4, external_links=1, images=3, robots_txt="present", sitemap_xml="missing"
    )


def _issue(**overrides: Any) -> Issue:
    base: dict[str, Any] = {
        "id": "title-missing",
        "category": "seo",
        "title": "Add a page title",
        "severity": "high",
        "confidence": 0.9,
        "evidence": {"type": "selector", "value": "head > title"},
        "source": "seo:title-missing",
        "why_it_matters": "Search results need a title.",
        "suggested_fix": "Add a 30 to 60 character title.",
        "impact_rank": 1,
    }
    base.update(overrides)
    return Issue.model_validate(base)


def _rewrite() -> Rewrite:
    return Rewrite(
        target="title",
        original="Acme Plumbing Co",
        variants=["Acme Plumbing in Austin", "Austin Plumbers, Same-Day Service"],
        label="AI generated, test before using",
    )


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    page: FetchedPage,
    seo: SeoAnalysis,
    pagespeed: PageSpeedAnalysis,
) -> None:
    def fake_prepare_fetch(raw_url: str, **kwargs: Any) -> FetchedPage:
        return page

    async def fake_fetch_page(cache_key: str, **kwargs: Any) -> FetchedPage:
        return page

    def fake_analyze_seo(html: str, final_url: str, **kwargs: Any) -> SeoAnalysis:
        return seo

    def fake_analyze_pagespeed(url: str, **kwargs: Any) -> PageSpeedAnalysis:
        return pagespeed

    def fake_enhance(issues: list[Issue], **kwargs: Any) -> AIResult:
        return AIResult(issues=issues, rewrites=[_rewrite()], limitations=[])

    monkeypatch.setattr("app.analyze.prepare_fetch", fake_prepare_fetch)
    monkeypatch.setattr("app.analyze.fetch_page", fake_fetch_page)
    monkeypatch.setattr("app.analyze.analyze_seo", fake_analyze_seo)
    monkeypatch.setattr("app.analyze.analyze_pagespeed", fake_analyze_pagespeed)
    monkeypatch.setattr("app.analyze.enhance_issues", fake_enhance)


def test_full_success_returns_ranked_report(client, monkeypatch):
    seo = SeoAnalysis(
        issues=[
            _issue(),
            _issue(
                id="meta-description-missing",
                title="Add a meta description",
                severity="medium",
                confidence=0.95,
                evidence={"type": "selector", "value": "head > meta[name=description]"},
                source="seo:meta-description-missing",
            ),
        ],
        stats=_stats(),
    )
    pagespeed = PageSpeedAnalysis(
        issues=[
            _issue(
                id="lcp-slow",
                category="performance",
                title="Largest Contentful Paint is slow",
                severity="medium",
                confidence=0.8,
                evidence={"type": "metric", "value": "LCP 4.2s"},
                source="pagespeed",
            )
        ],
        limitations=[],
    )
    _patch_pipeline(monkeypatch, page=_page(HTML), seo=seo, pagespeed=pagespeed)
    response = client.post("/api/analyze", json={"url": "https://example.com/"})
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == RESPONSE_KEYS
    assert body["data_quality"] == "full"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert [issue["id"] for issue in body["issues"]] == [
        "title-missing",
        "meta-description-missing",
        "lcp-slow",
    ]
    assert [issue["impact_rank"] for issue in body["issues"]] == [1, 2, 3]
    assert body["summary"] == (
        "Found 3 issues (1 high, 2 medium, 0 low). Top fix: Add a page title."
    )
    assert body["limitations"] == []
    assert body["score"]["value"] == 80
    assert {item["name"] for item in body["score"]["components"]} == {
        "high_issues",
        "medium_issues",
        "low_issues",
    }
    assert len(body["rewrites"]) == 1
    assert body["rewrites"][0]["label"] == "AI generated, test before using"
    AnalyzeResponse.model_validate(body)


def test_partial_when_pagespeed_reports_limitations(client, monkeypatch):
    seo = SeoAnalysis(issues=[_issue()], stats=_stats())
    pagespeed = PageSpeedAnalysis(
        issues=[], limitations=["Performance data unavailable (analysis timed out)."]
    )
    _patch_pipeline(monkeypatch, page=_page(HTML), seo=seo, pagespeed=pagespeed)
    response = client.post("/api/analyze", json={"url": "https://example.com/"})
    assert response.status_code == 200
    body = response.json()
    assert body["data_quality"] == "partial"
    assert body["score"] is None
    assert body["limitations"] == ["Performance data unavailable (analysis timed out)."]
    assert [issue["impact_rank"] for issue in body["issues"]] == [1]
    assert "(1 high, 0 medium, 0 low)" in body["summary"]
    assert len(body["rewrites"]) == 1


def test_og_only_short_circuits_before_analyzers(client, monkeypatch):
    page = _page(HTML, quality="og_only", tier=3)

    def fake_prepare_fetch(raw_url: str, **kwargs: Any) -> FetchedPage:
        return page

    async def fake_fetch_page(cache_key: str, **kwargs: Any) -> FetchedPage:
        return page

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("analyzer stage must not run for og_only")

    monkeypatch.setattr("app.analyze.prepare_fetch", fake_prepare_fetch)
    monkeypatch.setattr("app.analyze.fetch_page", fake_fetch_page)
    monkeypatch.setattr("app.analyze.analyze_seo", boom)
    monkeypatch.setattr("app.analyze.analyze_pagespeed", boom)
    monkeypatch.setattr("app.analyze.enhance_issues", boom)
    response = client.post("/api/analyze", json={"url": "https://example.com/"})
    assert response.status_code == 200
    body = response.json()
    assert body["data_quality"] == "og_only"
    assert body["issues"] == []
    assert body["rewrites"] == []
    assert body["score"] is None
    assert body["limitations"] == ["Only Open Graph tags could be read; full checks were skipped."]
    assert body["summary"] == "Only Open Graph tags could be read, so full checks were skipped."


def test_fetch_blocked_returns_typed_error(client, monkeypatch):
    def fake_prepare_fetch(raw_url: str, **kwargs: Any) -> FetchedPage:
        raise FetchError("FETCH_BLOCKED")

    monkeypatch.setattr("app.analyze.prepare_fetch", fake_prepare_fetch)
    response = client.post("/api/analyze", json={"url": "https://example.com/"})
    assert response.status_code == 502
    body = response.json()
    assert set(body.keys()) == {"code", "message", "retryable"}
    assert ErrorResponse.model_validate(body) == ErrorResponse(
        code="FETCH_BLOCKED",
        message="The site blocked automated fetching.",
        retryable=False,
    )


def test_invalid_url_returns_contract_error(client):
    response = client.post("/api/analyze", json={"url": "not-a-url"})
    assert response.status_code == 422
    assert ErrorResponse.model_validate(response.json()).code == "INVALID_URL"


def test_page_not_found_returns_typed_error(client, monkeypatch):
    def fake_prepare_fetch(raw_url: str, **kwargs: Any) -> FetchedPage:
        raise FetchError("FETCH_FAILED", "Page not found (404).")

    monkeypatch.setattr("app.analyze.prepare_fetch", fake_prepare_fetch)
    response = client.post("/api/analyze", json={"url": "https://example.com/gone"})
    assert response.status_code == 502
    body = response.json()
    assert set(body.keys()) == {"code", "message", "retryable"}
    assert ErrorResponse.model_validate(body) == ErrorResponse(
        code="FETCH_FAILED",
        message="Page not found (404).",
        retryable=False,
    )


def test_unexpected_pipeline_error_returns_internal_error(require_loop, monkeypatch):
    settings = Settings(
        frontend_origin="https://app.test", rate_limit_per_hour=100, log_level="WARNING"
    )
    quiet_client = TestClient(create_app(settings), raise_server_exceptions=False)

    async def fake_run_analysis(raw_url: str, **kwargs: Any) -> AnalyzeResponse:
        raise RuntimeError("boom")

    monkeypatch.setattr("app.main.run_analysis", fake_run_analysis)
    response = quiet_client.post("/api/analyze", json={"url": "https://example.com/"})
    assert response.status_code == 500
    body = response.json()
    assert set(body.keys()) == {"code", "message", "retryable"}
    assert ErrorResponse.model_validate(body).code == "INTERNAL_ERROR"


def test_second_request_serves_cached_analysis_with_fresh_request_id(client, monkeypatch):
    seo = SeoAnalysis(issues=[_issue()], stats=_stats())
    pagespeed = PageSpeedAnalysis(issues=[], limitations=[])
    _patch_pipeline(monkeypatch, page=_page(HTML), seo=seo, pagespeed=pagespeed)
    first = client.post(
        "/api/analyze",
        json={"url": "https://example.com/"},
        headers={"X-Request-ID": "first-request"},
    )
    second = client.post(
        "/api/analyze",
        json={"url": "https://example.com/"},
        headers={"X-Request-ID": "second-request"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["request_id"] == "first-request"
    assert second_body["request_id"] == "second-request"
    assert {k: v for k, v in second_body.items() if k != "request_id"} == {
        k: v for k, v in first_body.items() if k != "request_id"
    }


def test_youtube_video_returns_checklist_report(client, monkeypatch):
    watch_url = "https://www.youtube.com/watch?v=abc123"
    html = (
        "<html><head>"
        '<meta property="og:title" content="How to fix a leaking tap in 10 minutes">'
        '<meta property="og:description" content="Fix your tap today. Subscribe for more.">'
        '<meta property="og:image" content="https://i.ytimg.com/vi/abc123/hqdefault.jpg">'
        "</head><body></body></html>"
    )
    page = dataclasses.replace(_page(html), request_url=watch_url, final_url=watch_url)

    def fake_prepare_fetch(raw_url: str, **kwargs: Any) -> FetchedPage:
        return page

    async def fake_fetch_page(cache_key: str, **kwargs: Any) -> FetchedPage:
        return page

    monkeypatch.setattr("app.analyze.prepare_fetch", fake_prepare_fetch)
    monkeypatch.setattr("app.analyze.fetch_page", fake_fetch_page)
    response = client.post("/api/analyze", json={"url": watch_url})
    assert response.status_code == 200
    body = response.json()
    assert body["data_quality"] == "full"
    assert CHECKLIST_LIMITATION in body["limitations"]
    assert {issue["id"] for issue in body["issues"]} == {
        "youtube-links-missing",
        "youtube-captions-missing",
    }
    assert all(issue["source"].startswith("youtube-") for issue in body["issues"])
    assert body["score"] is not None
    assert body["rewrites"] == []
    assert "viral" not in response.text.casefold()
