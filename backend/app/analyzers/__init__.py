"""Fix It Proper analyzers package."""

from app.analyzers.pagespeed import PageSpeedAnalysis, analyze_pagespeed
from app.analyzers.scoring import ScoredResult, build_report, compute_score, rank_issues
from app.analyzers.seo import SeoAnalysis, SeoStats, analyze_seo

__all__ = [
    "PageSpeedAnalysis",
    "ScoredResult",
    "SeoAnalysis",
    "SeoStats",
    "analyze_pagespeed",
    "analyze_seo",
    "build_report",
    "compute_score",
    "rank_issues",
]
