"""PageSpeed analyzer tests over recorded JSON responses. No loop needed."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from app.analyzers.pagespeed import PageSpeedAnalysis, analyze_pagespeed
from app.cache.store import FetchCache
from app.config import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "pagespeed"
URL = "https://example.com/"


def _settings() -> Settings:
    return Settings(log_level="WARNING", pagespeed_api_key="test-key")


def _cache() -> FetchCache[PageSpeedAnalysis]:
    return FetchCache(ttl_seconds=86400, max_total_bytes=10_000_000)


def _payload(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _json_client(
    payload: dict[str, Any], status: int = 200
) -> tuple[httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=payload)

    return _client(handler), seen


def test_missing_key_skips_without_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call API without key")

    settings = Settings(log_level="WARNING", pagespeed_api_key="")
    result = analyze_pagespeed(URL, settings=settings, client=_client(handler), cache=_cache())
    assert result.issues == []
    assert result.limitations == ["Performance data unavailable"]


def test_full_response_maps_metrics_and_top_audits():
    client, _ = _json_client(_payload("psi_full.json"))
    result = analyze_pagespeed(URL, settings=_settings(), client=client, cache=_cache())
    ids = [issue.id for issue in result.issues]
    assert ids == [
        "pagespeed-lcp",
        "pagespeed-responsiveness",
        "pagespeed-byte-weight",
        "pagespeed-audit-uses-http2",
        "pagespeed-audit-render-blocking-resources",
        "pagespeed-audit-unused-javascript",
        "pagespeed-audit-uses-responsive-images",
        "pagespeed-audit-server-response-time",
    ]
    by_id = {issue.id: issue for issue in result.issues}
    assert by_id["pagespeed-lcp"].severity == "high"
    assert by_id["pagespeed-responsiveness"].severity == "medium"
    assert "INP" in by_id["pagespeed-responsiveness"].evidence.value
    assert by_id["pagespeed-byte-weight"].severity == "high"
    assert by_id["pagespeed-audit-uses-http2"].severity == "high"
    assert by_id["pagespeed-audit-server-response-time"].severity == "medium"
    for issue in result.issues:
        assert issue.source == "pagespeed"
        assert issue.evidence.type == "metric"
        assert issue.category == "performance"
    assert [issue.impact_rank for issue in result.issues] == list(range(1, 9))
    assert result.limitations == []
    assert "4.8 s" in by_id["pagespeed-lcp"].evidence.value
    blocking = by_id["pagespeed-audit-render-blocking-resources"]
    assert "Potential savings of 1,200 ms" in blocking.evidence.value
    assert "https://web.dev" not in blocking.why_it_matters
    assert "Learn more" in blocking.why_it_matters


def test_no_inp_falls_back_to_tbt():
    client, _ = _json_client(_payload("psi_no_inp.json"))
    result = analyze_pagespeed(URL, settings=_settings(), client=client, cache=_cache())
    ids = [issue.id for issue in result.issues]
    assert ids == ["pagespeed-responsiveness", "pagespeed-audit-uses-http2"]
    responsiveness = result.issues[0]
    assert responsiveness.severity == "high"
    assert "TBT" in responsiveness.evidence.value
    assert "410 ms" in responsiveness.evidence.value


def test_passing_response_yields_no_issues():
    client, _ = _json_client(_payload("psi_passing.json"))
    result = analyze_pagespeed(URL, settings=_settings(), client=client, cache=_cache())
    assert result.issues == []
    assert result.limitations == []


def test_retries_once_on_5xx():
    calls: list[str] = []
    payload = _payload("psi_passing.json")

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append("call")
        if len(calls) == 1:
            return httpx.Response(500)
        return httpx.Response(200, json=payload)

    result = analyze_pagespeed(
        URL, settings=_settings(), client=_client(handler), cache=_cache(), retry_delay_s=0
    )
    assert len(calls) == 2
    assert result.issues == []
    assert result.limitations == []


def test_persistent_5xx_yields_limitation():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append("call")
        return httpx.Response(503)

    result = analyze_pagespeed(
        URL, settings=_settings(), client=_client(handler), cache=_cache(), retry_delay_s=0
    )
    assert len(calls) == 2
    assert result.issues == []
    assert result.limitations == ["Performance data unavailable"]


def test_429_is_quota_without_retry():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append("call")
        return httpx.Response(429)

    result = analyze_pagespeed(URL, settings=_settings(), client=_client(handler), cache=_cache())
    assert len(calls) == 1
    assert result.issues == []
    assert result.limitations == ["Performance data temporarily unavailable (API quota reached)."]


def test_403_quota_body_is_quota():
    client, seen = _json_client(_payload("psi_quota_403.json"), status=403)
    result = analyze_pagespeed(URL, settings=_settings(), client=client, cache=_cache())
    assert len(seen) == 1
    assert result.limitations == ["Performance data temporarily unavailable (API quota reached)."]


def test_403_other_is_generic():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"forbidden")

    result = analyze_pagespeed(URL, settings=_settings(), client=_client(handler), cache=_cache())
    assert result.limitations == ["Performance data unavailable"]


def test_timeout_yields_limitation_without_retry():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append("call")
        raise httpx.TimeoutException("slow")

    result = analyze_pagespeed(URL, settings=_settings(), client=_client(handler), cache=_cache())
    assert len(calls) == 1
    assert result.issues == []
    assert result.limitations == ["Performance data unavailable"]


def test_unexpected_shape_yields_limitation():
    client, _ = _json_client(_payload("psi_empty.json"))
    result = analyze_pagespeed(URL, settings=_settings(), client=client, cache=_cache())
    assert result.issues == []
    assert result.limitations == ["Performance data unavailable"]


def test_request_shape():
    client, seen = _json_client(_payload("psi_passing.json"))
    analyze_pagespeed(URL, settings=_settings(), client=client, cache=_cache())
    assert len(seen) == 1
    params = seen[0].url.params
    assert params["strategy"] == "mobile"
    assert params.get_list("category") == [
        "performance",
        "accessibility",
        "best-practices",
        "seo",
    ]
    assert params["key"] == "test-key"
    assert params["url"] == URL


def test_results_cached_per_url():
    payload = _payload("psi_passing.json")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=payload)

    cache = _cache()
    client = _client(handler)
    first = analyze_pagespeed(URL, settings=_settings(), client=client, cache=cache)
    second = analyze_pagespeed(URL, settings=_settings(), client=client, cache=cache)
    assert first.cached is False
    assert second.cached is True
    assert len(calls) == 1
    analyze_pagespeed("https://other.com/", settings=_settings(), client=client, cache=cache)
    assert len(calls) == 2


def test_failures_not_cached():
    calls: list[str] = []
    payload = _payload("psi_passing.json")

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append("call")
        if len(calls) <= 2:
            return httpx.Response(500)
        return httpx.Response(200, json=payload)

    cache = _cache()
    client = _client(handler)
    first = analyze_pagespeed(
        URL, settings=_settings(), client=client, cache=cache, retry_delay_s=0
    )
    assert first.limitations == ["Performance data unavailable"]
    second = analyze_pagespeed(
        URL, settings=_settings(), client=client, cache=cache, retry_delay_s=0
    )
    assert second.limitations == []
    assert len(calls) == 3
