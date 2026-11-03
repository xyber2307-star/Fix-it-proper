"""Scoring tests with golden snapshots. No loop needed."""

import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.analyzers.pagespeed import PageSpeedAnalysis, analyze_pagespeed
from app.analyzers.scoring import (
    ScoredResult,
    build_report,
    collect_limitations,
    compute_score,
    rank_issues,
)
from app.analyzers.seo import analyze_seo
from app.analyzers.youtube import (
    CHECKLIST_LIMITATION,
    TRANSCRIPT_UNKNOWN_LIMITATION,
    TranscriptStatus,
    YoutubeAnalysis,
    YoutubeData,
)
from app.cache.store import FetchCache
from app.config import Settings
from app.schemas import Evidence, Issue, Severity

SNAPSHOTS = Path(__file__).parent / "fixtures" / "scoring"
FETCHER_FIXTURES = Path(__file__).parent / "fixtures" / "fetcher"
PAGESPEED_FIXTURES = Path(__file__).parent / "fixtures" / "pagespeed"
URL = "https://example.com/"


def _issue(
    issue_id: str, severity: Severity, confidence: float, evidence: str | None = None
) -> Issue:
    return Issue(
        id=issue_id,
        category="seo",
        title=f"Title {issue_id}",
        severity=severity,
        confidence=confidence,
        evidence=Evidence(type="text", value=evidence or f"evidence {issue_id}"),
        source=issue_id,
        why_it_matters="why",
        suggested_fix="fix",
        impact_rank=1,
    )


def _snapshot_payload(result: ScoredResult) -> dict[str, Any]:
    issues = [
        {
            "id": issue.id,
            "severity": issue.severity,
            "confidence": issue.confidence,
            "impact_rank": issue.impact_rank,
            "evidence": issue.evidence.value,
        }
        for issue in result.issues
    ]
    score = result.score.model_dump(mode="json") if result.score is not None else None
    return {"issues": issues, "limitations": result.limitations, "score": score}


def _check_snapshot(name: str, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path = SNAPSHOTS / name
    if os.environ.get("UPDATE_SNAPSHOTS") == "1" or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == text


def _seo_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _psi_payload() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (PAGESPEED_FIXTURES / "psi_full.json").read_text(encoding="utf-8")
    )
    return data


def _psi_client(payload: dict[str, Any]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _explode_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_rank_orders_by_weight_times_confidence():
    ranked = rank_issues(
        [_issue("seo-lang", "low", 1.0), _issue("seo-viewport", "high", 0.5)],
        [_issue("seo-canonical-missing", "medium", 1.0)],
    )
    assert [issue.id for issue in ranked] == [
        "seo-canonical-missing",
        "seo-viewport",
        "seo-lang",
    ]
    assert [issue.impact_rank for issue in ranked] == [1, 2, 3]


def test_ties_break_by_ease():
    ranked = rank_issues(
        [
            _issue("seo-structured-data-missing", "medium", 1.0),
            _issue("seo-canonical-missing", "medium", 1.0),
        ],
        [],
    )
    assert [issue.id for issue in ranked] == [
        "seo-canonical-missing",
        "seo-structured-data-missing",
    ]


def test_ties_break_by_id():
    ranked = rank_issues(
        [],
        [
            _issue("pagespeed-audit-zebra", "medium", 1.0),
            _issue("pagespeed-audit-apple", "medium", 1.0),
        ],
    )
    assert [issue.id for issue in ranked] == [
        "pagespeed-audit-apple",
        "pagespeed-audit-zebra",
    ]


def test_dedupe_keeps_first_by_id():
    ranked = rank_issues(
        [_issue("seo-lang", "low", 1.0, evidence="seo copy")],
        [
            _issue("seo-lang", "low", 1.0, evidence="pagespeed copy"),
            _issue("seo-viewport", "high", 1.0),
        ],
    )
    assert [issue.id for issue in ranked] == ["seo-viewport", "seo-lang"]
    assert ranked[1].evidence.value == "seo copy"


def test_score_math():
    ranked = rank_issues(
        [
            _issue("seo-viewport", "high", 1.0),
            _issue("seo-title-missing", "high", 1.0),
            _issue("seo-canonical-missing", "medium", 1.0),
            _issue("seo-lang", "low", 1.0),
        ],
        [],
    )
    score = compute_score(ranked, "full")
    assert score is not None
    assert score.value == 73.0
    assert score.formula_version == "v1.0"
    assert [component.model_dump() for component in score.components] == [
        {"name": "high_issues", "value": 20.0, "weight": 0.1},
        {"name": "medium_issues", "value": 5.0, "weight": 0.05},
        {"name": "low_issues", "value": 2.0, "weight": 0.02},
    ]


def test_score_floors_at_zero():
    ranked = rank_issues([_issue(f"extra-{index}", "high", 1.0) for index in range(20)], [])
    score = compute_score(ranked, "full")
    assert score is not None
    assert score.value == 0.0


@pytest.mark.parametrize("quality", ["partial", "og_only"])
def test_score_null_unless_full(quality):
    ranked = rank_issues([_issue("seo-lang", "low", 1.0)], [])
    assert compute_score(ranked, quality) is None
    assert compute_score(ranked, "full") is not None


def test_collect_limitations():
    seo = analyze_seo("<html></html>", URL, http_client=_explode_client())
    settings = Settings(log_level="WARNING", pagespeed_api_key="")
    pagespeed = analyze_pagespeed(URL, settings=settings)
    assert collect_limitations(seo, pagespeed) == [
        "Performance data unavailable",
        "robots.txt status could not be verified.",
        "sitemap.xml status could not be verified.",
    ]


def test_collect_limitations_dedupes():
    seo = analyze_seo("<html></html>", URL, http_client=_seo_client())
    pagespeed = PageSpeedAnalysis(issues=[], limitations=["Performance data unavailable"] * 2)
    assert collect_limitations(seo, pagespeed) == ["Performance data unavailable"]


def _ranking_input() -> tuple[list[Issue], list[Issue]]:
    seo = [
        _issue("seo-viewport", "high", 0.5),
        _issue("seo-lang", "low", 1.0),
        _issue("seo-canonical-missing", "medium", 1.0),
    ]
    pagespeed = [
        _issue("pagespeed-lcp", "high", 0.9),
        _issue("seo-lang", "low", 1.0, evidence="dupe copy"),
    ]
    return seo, pagespeed


def _ranked_payload() -> dict[str, Any]:
    seo, pagespeed = _ranking_input()
    ranked = rank_issues(seo, pagespeed)
    result = ScoredResult(
        issues=ranked,
        limitations=["sample limitation"],
        score=compute_score(ranked, "full"),
    )
    return _snapshot_payload(result)


def test_snapshot_ranking_deterministic():
    assert _ranked_payload() == _ranked_payload()


def test_snapshot_ranking_golden():
    _check_snapshot("snapshot_ranking.json", _ranked_payload())


def test_snapshot_e2e():
    html = (FETCHER_FIXTURES / "full_page.html").read_text(encoding="utf-8")
    url = "https://plumbing.example/"
    seo = analyze_seo(html, url, http_client=_seo_client())
    settings = Settings(log_level="WARNING", pagespeed_api_key="test-key")
    cache: FetchCache[PageSpeedAnalysis] = FetchCache(ttl_seconds=86400, max_total_bytes=10_000_000)
    pagespeed = analyze_pagespeed(
        url, settings=settings, client=_psi_client(_psi_payload()), cache=cache
    )
    result = build_report(seo, pagespeed, "full")
    assert result.score is not None
    assert result.limitations == []
    _check_snapshot("snapshot_e2e.json", _snapshot_payload(result))


def _youtube_analysis(
    status: TranscriptStatus = "retrieved", issues: list[Issue] | None = None
) -> YoutubeAnalysis:
    data = YoutubeData(
        video_id="abc123",
        title="How to fix a leaking tap in 10 minutes at home",
        description="Fix your leaking tap today with parts from any hardware store.",
        thumbnail_url="https://i.ytimg.com/vi/abc123/hqdefault.jpg",
        duration_s=300,
        tracks=(),
        transcript="hello" if status == "retrieved" else None,
        transcript_status=status,
    )
    return YoutubeAnalysis(issues=list(issues) if issues is not None else [], data=data)


def test_rank_merges_youtube_issues():
    ranked = rank_issues(
        [_issue("seo-lang", "low", 1.0)],
        [_issue("pagespeed-cls", "medium", 0.6)],
        [_issue("youtube-cta-missing", "high", 1.0)],
    )
    assert [issue.id for issue in ranked] == [
        "youtube-cta-missing",
        "pagespeed-cls",
        "seo-lang",
    ]
    assert [issue.impact_rank for issue in ranked] == [1, 2, 3]


def test_dedupe_prefers_seo_over_youtube():
    ranked = rank_issues(
        [_issue("dupe-id", "low", 1.0, evidence="seo copy")],
        [],
        [_issue("dupe-id", "high", 1.0, evidence="youtube copy")],
    )
    assert [issue.id for issue in ranked] == ["dupe-id"]
    assert ranked[0].evidence.value == "seo copy"


def test_collect_limitations_adds_youtube_disclaimer():
    seo = analyze_seo("<html></html>", URL, http_client=_seo_client())
    pagespeed = PageSpeedAnalysis(issues=[], limitations=[])
    assert collect_limitations(seo, pagespeed, _youtube_analysis()) == [CHECKLIST_LIMITATION]


def test_collect_limitations_flags_unknown_transcript():
    seo = analyze_seo("<html></html>", URL, http_client=_seo_client())
    pagespeed = PageSpeedAnalysis(issues=[], limitations=[])
    youtube = _youtube_analysis(status="unknown")
    assert collect_limitations(seo, pagespeed, youtube) == [
        CHECKLIST_LIMITATION,
        TRANSCRIPT_UNKNOWN_LIMITATION,
    ]


def _youtube_report() -> ScoredResult:
    seo = analyze_seo("<html></html>", URL, http_client=_seo_client())
    pagespeed = PageSpeedAnalysis(issues=[], limitations=[])
    youtube = _youtube_analysis(issues=[_issue("youtube-cta-missing", "low", 0.7)])
    return build_report(seo, pagespeed, "full", youtube=youtube)


def test_snapshot_youtube_deterministic():
    assert _snapshot_payload(_youtube_report()) == _snapshot_payload(_youtube_report())


def test_snapshot_youtube_golden():
    _check_snapshot("snapshot_youtube.json", _snapshot_payload(_youtube_report()))
