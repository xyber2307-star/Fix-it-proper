"""Merge, rank, and score analyzer issues.

Rank formula: rank_score = SEVERITY_WEIGHT[severity] * confidence.
Higher rank_score ranks first. Ties break by ease of fix (lower
_EASE_BY_RULE_ID first), then by rule id ascending so output is
deterministic for the same input. SEO issues merge first, then
PageSpeed, then YouTube; the first issue wins on duplicate rule ids.

Score formula: value = max(0, 100 - (10 * highs + 5 * mediums + 2 * lows)).
Components carry per-severity deductions so the UI can replay the math.
Score is None unless data_quality is "full".
"""

from dataclasses import dataclass

from app.analyzers.pagespeed import PageSpeedAnalysis
from app.analyzers.seo import SeoAnalysis
from app.analyzers.youtube import (
    CHECKLIST_LIMITATION,
    TRANSCRIPT_UNKNOWN_LIMITATION,
    YoutubeAnalysis,
)
from app.schemas import DataQuality, Issue, Score, ScoreComponent

SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}
PENALTY_BY_SEVERITY = {"high": 10, "medium": 5, "low": 2}
FORMULA_VERSION = "v1.0"
_DEFAULT_EASE = 2

# 1 = quick (add or remove a tag), 2 = moderate (write copy, edit many
# tags), 3 = involved (infrastructure or schema work). Unknown rule ids,
# including pagespeed-audit-* checks, use _DEFAULT_EASE.
_EASE_BY_RULE_ID = {
    "seo-title-missing": 1,
    "seo-title-empty": 1,
    "seo-title-length": 2,
    "seo-title-duplicate-h1": 2,
    "seo-meta-description-missing": 2,
    "seo-meta-description-length": 2,
    "seo-h1-missing": 2,
    "seo-h1-multiple": 1,
    "seo-heading-order": 2,
    "seo-canonical-missing": 1,
    "seo-canonical-host": 1,
    "seo-robots-noindex": 1,
    "seo-img-alt": 2,
    "seo-img-dimensions": 2,
    "seo-og-title": 1,
    "seo-og-description": 2,
    "seo-og-image": 1,
    "seo-twitter-card": 1,
    "seo-viewport": 1,
    "seo-lang": 1,
    "seo-link-empty-text": 2,
    "seo-link-bad-href": 2,
    "seo-structured-data-missing": 3,
    "seo-jsonld-invalid": 2,
    "seo-robots-txt": 2,
    "seo-sitemap": 2,
    "seo-https": 3,
    "seo-mixed-content": 2,
    "pagespeed-lcp": 3,
    "pagespeed-cls": 2,
    "pagespeed-responsiveness": 3,
    "pagespeed-byte-weight": 3,
    "youtube-title-missing": 1,
    "youtube-title-empty": 2,
    "youtube-title-length": 2,
    "youtube-description-missing": 2,
    "youtube-description-hook": 2,
    "youtube-cta-missing": 1,
    "youtube-links-missing": 1,
    "youtube-chapters-missing": 2,
    "youtube-thumbnail-missing": 1,
    "youtube-captions-missing": 2,
}


@dataclass(frozen=True)
class ScoredResult:
    """Ranked issues plus limitations and the optional score."""

    issues: list[Issue]
    limitations: list[str]
    score: Score | None


def _ease_of(rule_id: str) -> int:
    return _EASE_BY_RULE_ID.get(rule_id, _DEFAULT_EASE)


def _rank_key(item: Issue) -> tuple[float, int, str]:
    weight = SEVERITY_WEIGHT[item.severity] * item.confidence
    return (-weight, _ease_of(item.id), item.id)


def rank_issues(
    seo_issues: list[Issue],
    pagespeed_issues: list[Issue],
    youtube_issues: list[Issue] | None = None,
) -> list[Issue]:
    """Merge all lists, drop later duplicates by id, rank, number 1..N."""
    seen: set[str] = set()
    merged: list[Issue] = []
    for issue in (*seo_issues, *pagespeed_issues, *(youtube_issues or [])):
        if issue.id in seen:
            continue
        seen.add(issue.id)
        merged.append(issue)
    merged.sort(key=_rank_key)
    for rank, issue in enumerate(merged, start=1):
        issue.impact_rank = rank
    return merged


def compute_score(ranked: list[Issue], data_quality: DataQuality) -> Score | None:
    """Apply the score formula, or None when data is incomplete."""
    if data_quality != "full":
        return None
    counts = {"high": 0, "medium": 0, "low": 0}
    for issue in ranked:
        counts[issue.severity] += 1
    components = [
        ScoreComponent(
            name=f"{severity}_issues",
            value=float(counts[severity] * PENALTY_BY_SEVERITY[severity]),
            weight=PENALTY_BY_SEVERITY[severity] / 100,
        )
        for severity in ("high", "medium", "low")
    ]
    total = sum(component.value for component in components)
    return Score(
        value=max(0.0, 100.0 - total),
        formula_version=FORMULA_VERSION,
        components=components,
    )


def collect_limitations(
    seo: SeoAnalysis, pagespeed: PageSpeedAnalysis, youtube: YoutubeAnalysis | None = None
) -> list[str]:
    """Pass through PageSpeed limits and add unverified crawl files."""
    limitations = list(pagespeed.limitations)
    if seo.stats.robots_txt == "unknown":
        limitations.append("robots.txt status could not be verified.")
    if seo.stats.sitemap_xml == "unknown":
        limitations.append("sitemap.xml status could not be verified.")
    if youtube is not None:
        limitations.append(CHECKLIST_LIMITATION)
        if youtube.data.transcript_status == "unknown":
            limitations.append(TRANSCRIPT_UNKNOWN_LIMITATION)
    return list(dict.fromkeys(limitations))


def build_report(
    seo: SeoAnalysis,
    pagespeed: PageSpeedAnalysis,
    data_quality: DataQuality,
    youtube: YoutubeAnalysis | None = None,
) -> ScoredResult:
    """Rank merged issues, compute the optional score, gather limitations."""
    ranked = rank_issues(seo.issues, pagespeed.issues, youtube.issues if youtube else None)
    return ScoredResult(
        issues=ranked,
        limitations=collect_limitations(seo, pagespeed, youtube),
        score=compute_score(ranked, data_quality),
    )
