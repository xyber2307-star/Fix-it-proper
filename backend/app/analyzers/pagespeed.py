"""PageSpeed Insights analyzer using real Google lab data only.

Calls the mobile runPagespeed endpoint, maps lab metrics and the worst
failing audits to issues, and degrades to a limitation entry whenever
the API key is missing or the call fails. Speed is never estimated
from our own timing.
"""

import dataclasses
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.brand import SLUG
from app.cache.store import FetchCache
from app.config import Settings, get_settings
from app.schemas import Evidence, Issue, Severity

logger = logging.getLogger(f"{SLUG}.pagespeed")

API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
STRATEGY = "mobile"
CATEGORIES = ("performance", "accessibility", "best-practices", "seo")
REQUEST_TIMEOUT_S = 30.0
CACHE_TTL_S = 86400
CACHE_MAX_BYTES = 32 * 1024 * 1024
CACHE_MAX_ENTRIES = 200
NO_DATA = "Performance data unavailable"
QUOTA_LIMITATION = "Performance data temporarily unavailable (API quota reached)."

_QUOTA_REASONS = frozenset(
    {
        "dailyLimitExceeded",
        "quotaExceeded",
        "rateLimitExceeded",
        "userRateLimitExceeded",
    }
)
_METRIC_AUDIT_IDS = frozenset(
    {
        "largest-contentful-paint",
        "cumulative-layout-shift",
        "interaction-to-next-paint",
        "total-blocking-time",
        "total-byte-weight",
    }
)
_FAIL_MODES = frozenset({"binary", "numeric", "metricSavings"})
_TOP_AUDITS = 5

_shared_cache: FetchCache["PageSpeedAnalysis"] | None = None


@dataclass(frozen=True)
class PageSpeedAnalysis:
    """PageSpeed issues plus limitations for the orchestrator to merge."""

    issues: list[Issue]
    limitations: list[str]
    cached: bool = False


def _get_shared_cache() -> FetchCache["PageSpeedAnalysis"]:
    global _shared_cache
    if _shared_cache is None:
        _shared_cache = FetchCache(
            ttl_seconds=CACHE_TTL_S,
            max_total_bytes=CACHE_MAX_BYTES,
            max_entries=CACHE_MAX_ENTRIES,
        )
    return _shared_cache


def _host_of(url: str) -> str:
    try:
        return urlsplit(url).hostname or "unknown"
    except ValueError:
        return "unknown"


def _audit_score(audit: dict[str, Any]) -> float | None:
    score = audit.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    return float(score)


def _metric_display(audit: dict[str, Any]) -> str:
    display = audit.get("displayValue")
    if isinstance(display, str) and display.strip():
        return display.strip()
    numeric = audit.get("numericValue")
    if isinstance(numeric, bool) or not isinstance(numeric, (int, float)):
        return "no value"
    unit = audit.get("numericUnit")
    suffix = f" {unit}" if isinstance(unit, str) and unit.strip() else ""
    return f"{numeric}{suffix}"


def _metric_issue(
    slug: str,
    label: str,
    title: str,
    why_it_matters: str,
    suggested_fix: str,
    audit: dict[str, Any] | None,
) -> Issue | None:
    if audit is None:
        return None
    score = _audit_score(audit)
    if score is None or score >= 0.9:
        return None
    severity: Severity = "high" if score < 0.5 else "medium"
    return Issue(
        id=f"pagespeed-{slug}",
        category="performance",
        title=title,
        severity=severity,
        confidence=0.9,
        evidence=Evidence(type="metric", value=f"{label} {_metric_display(audit)} (score {score})"),
        source="pagespeed",
        why_it_matters=why_it_matters,
        suggested_fix=suggested_fix,
        impact_rank=1,
    )


def _audit_by_id(audits: dict[str, Any], audit_id: str) -> dict[str, Any] | None:
    audit = audits.get(audit_id)
    return audit if isinstance(audit, dict) else None


def _metric_issues(audits: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    lcp = _metric_issue(
        "lcp",
        "LCP",
        "Largest Contentful Paint is slow",
        "Visitors wait too long before the main content appears.",
        "Compress images, preload the hero image, and speed up the server response.",
        _audit_by_id(audits, "largest-contentful-paint"),
    )
    if lcp is not None:
        issues.append(lcp)
    cls = _metric_issue(
        "cls",
        "CLS",
        "Layout shifts while loading",
        "Shifting layout makes visitors tap the wrong thing.",
        "Set sizes on images and embeds and reserve space for late loading content.",
        _audit_by_id(audits, "cumulative-layout-shift"),
    )
    if cls is not None:
        issues.append(cls)
    responsiveness = _audit_by_id(audits, "interaction-to-next-paint")
    label = "INP"
    if responsiveness is None:
        responsiveness = _audit_by_id(audits, "total-blocking-time")
        label = "TBT"
    slow_response = _metric_issue(
        "responsiveness",
        label,
        "Page responds slowly to input",
        "The page responds slowly to taps and clicks.",
        "Reduce JavaScript work on load and defer non-critical scripts.",
        responsiveness,
    )
    if slow_response is not None:
        issues.append(slow_response)
    weight = _metric_issue(
        "byte-weight",
        "Page weight",
        "Page downloads too many bytes",
        "Heavy pages load slowly on mobile networks.",
        "Compress images, trim unused code, and serve modern formats.",
        _audit_by_id(audits, "total-byte-weight"),
    )
    if weight is not None:
        issues.append(weight)
    return issues


def _clean_description(audit: dict[str, Any]) -> str:
    raw = audit.get("description")
    text = raw if isinstance(raw, str) else ""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = " ".join(text.split())
    if len(text) > 240:
        text = text[:240] + "..."
    return text or "This check failed in the mobile PageSpeed test."


def _failing_audit_issues(audits: dict[str, Any]) -> list[Issue]:
    candidates: list[tuple[float, str, dict[str, Any]]] = []
    for audit_id, audit in audits.items():
        if not isinstance(audit_id, str) or not isinstance(audit, dict):
            continue
        if audit_id in _METRIC_AUDIT_IDS:
            continue
        if audit.get("scoreDisplayMode") not in _FAIL_MODES:
            continue
        score = _audit_score(audit)
        if score is None or score >= 0.9:
            continue
        candidates.append((score, audit_id, audit))
    candidates.sort(key=lambda item: (item[0], item[1]))
    issues: list[Issue] = []
    for score, audit_id, audit in candidates[:_TOP_AUDITS]:
        severity: Severity = "high" if score < 0.5 else "medium"
        display = audit.get("displayValue")
        if isinstance(display, str) and display.strip():
            evidence = f"{display.strip()} (score {score})"
        else:
            evidence = f"score {score}"
        title = audit.get("title")
        title_text = title.strip() if isinstance(title, str) and title.strip() else audit_id
        issues.append(
            Issue(
                id=f"pagespeed-audit-{audit_id}",
                category="performance",
                title=title_text,
                severity=severity,
                confidence=0.9,
                evidence=Evidence(type="metric", value=evidence),
                source="pagespeed",
                why_it_matters=_clean_description(audit),
                suggested_fix="Apply the PageSpeed recommendation for this check, then re-test.",
                impact_rank=1,
            )
        )
    return issues


def _is_quota_body(response: httpx.Response) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    errors = error.get("errors")
    if not isinstance(errors, list):
        return False
    for entry in errors:
        if isinstance(entry, dict) and entry.get("reason") in _QUOTA_REASONS:
            return True
    return False


def _request_params(page_url: str, api_key: str) -> dict[str, str | list[str]]:
    return {
        "url": page_url,
        "key": api_key,
        "strategy": STRATEGY,
        "category": list(CATEGORIES),
    }


def _fetch_payload(
    client: httpx.Client, page_url: str, api_key: str, retry_delay_s: float
) -> tuple[dict[str, Any] | None, str | None]:
    """GET the runPagespeed endpoint with one retry on 5xx.

    Returns the parsed payload or a limitation message. Never raises
    for API side failures.
    """
    host = _host_of(page_url)
    for attempt in (0, 1):
        try:
            response = client.get(
                API_URL,
                params=_request_params(page_url, api_key),
                timeout=REQUEST_TIMEOUT_S,
            )
        except httpx.HTTPError as exc:
            logger.warning("pagespeed request failed", extra={"reason": str(exc), "url_host": host})
            return None, NO_DATA
        if response.status_code == 429:
            logger.warning("pagespeed quota hit", extra={"url_host": host})
            return None, QUOTA_LIMITATION
        if response.status_code == 403:
            if _is_quota_body(response):
                logger.warning("pagespeed quota hit", extra={"url_host": host})
                return None, QUOTA_LIMITATION
            logger.warning("pagespeed forbidden", extra={"reason": "403", "url_host": host})
            return None, NO_DATA
        if response.status_code >= 500:
            logger.warning(
                "pagespeed server error",
                extra={"reason": str(response.status_code), "url_host": host},
            )
            if attempt == 0:
                time.sleep(retry_delay_s)
                continue
            return None, NO_DATA
        if response.status_code != 200:
            logger.warning(
                "pagespeed request failed",
                extra={"reason": str(response.status_code), "url_host": host},
            )
            return None, NO_DATA
        try:
            payload = response.json()
        except ValueError:
            return None, NO_DATA
        if not isinstance(payload, dict):
            return None, NO_DATA
        return payload, None
    return None, NO_DATA


def _analysis_size(analysis: PageSpeedAnalysis) -> int:
    body = json.dumps([issue.model_dump(mode="json") for issue in analysis.issues])
    return len(body.encode("utf-8")) + sum(len(item) for item in analysis.limitations) + 256


def analyze_pagespeed(
    url: str,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
    cache: FetchCache[PageSpeedAnalysis] | None = None,
    retry_delay_s: float = 1.0,
) -> PageSpeedAnalysis:
    """Analyze a URL with PageSpeed Insights, degrading gracefully."""
    resolved = settings or get_settings()
    api_key = (resolved.pagespeed_api_key or "").strip()
    if not api_key:
        return PageSpeedAnalysis(issues=[], limitations=[NO_DATA])
    page_url = url.strip()
    active_cache = cache if cache is not None else _get_shared_cache()
    cache_key = f"pagespeed:{page_url}"
    cached = active_cache.get(cache_key)
    if cached is not None:
        return dataclasses.replace(cached, cached=True)
    owned = client is None
    active = client if client is not None else httpx.Client(timeout=REQUEST_TIMEOUT_S)
    try:
        payload, failure = _fetch_payload(active, page_url, api_key, retry_delay_s)
    finally:
        if owned:
            active.close()
    if failure is not None or payload is None:
        return PageSpeedAnalysis(issues=[], limitations=[failure or NO_DATA])
    lighthouse = payload.get("lighthouseResult")
    if not isinstance(lighthouse, dict):
        return PageSpeedAnalysis(issues=[], limitations=[NO_DATA])
    audits = lighthouse.get("audits")
    if not isinstance(audits, dict):
        return PageSpeedAnalysis(issues=[], limitations=[NO_DATA])
    issues = _metric_issues(audits)
    issues.extend(_failing_audit_issues(audits))
    for rank, issue in enumerate(issues, start=1):
        issue.impact_rank = rank
    analysis = PageSpeedAnalysis(issues=issues, limitations=[])
    active_cache.set(cache_key, analysis, _analysis_size(analysis))
    return analysis
