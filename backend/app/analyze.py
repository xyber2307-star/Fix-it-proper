"""End-to-end analysis pipeline wiring fetch, analyzers, scoring, and AI.

Flow: validate and guard, analysis cache check, fetch, SEO plus
PageSpeed in parallel, score and rank, AI layer, assemble the
response, cache, return. Slow PageSpeed or AI stages degrade to
limitations instead of failing the request. YouTube video URLs take
a checklist branch instead of the SEO plus PageSpeed path.
"""

import asyncio
import logging
from datetime import UTC, datetime

import httpx

from app.ai.client import AIClient
from app.ai.service import AIResult, RewriteOriginals, enhance_issues
from app.analyzers.pagespeed import PageSpeedAnalysis, analyze_pagespeed
from app.analyzers.scoring import ScoredResult, build_report
from app.analyzers.seo import SeoAnalysis, SeoStats, analyze_seo
from app.analyzers.youtube import (
    YoutubeData,
    analyze_youtube,
    extract_cta_line,
    first_description_line,
    is_youtube_video_url,
)
from app.brand import SLUG
from app.cache.store import FetchCache
from app.config import Settings, get_settings
from app.fetcher.extract import extract_page_text, extract_primary_cta
from app.fetcher.models import FetchedPage, FetchError
from app.fetcher.playwright_fetcher import BrowserManager
from app.fetcher.service import fetch_page, prepare_fetch
from app.schemas import AnalyzeResponse, DataQuality, Issue

logger = logging.getLogger(f"{SLUG}.analyze")

TOTAL_BUDGET_S = 40.0
PAGESPEED_BUDGET_S = 25.0
AI_BUDGET_S = 15.0

_OG_LIMITATION = "Only Open Graph tags could be read; full checks were skipped."
_OG_SUMMARY = "Only Open Graph tags could be read, so full checks were skipped."
_PAGESPEED_TIMEOUT = "Performance data unavailable (analysis timed out)."
_AI_TIMEOUT = "AI explanations unavailable (analysis timed out)."

_shared_analysis_cache: FetchCache[AnalyzeResponse] | None = None


def _get_shared_analysis_cache(settings: Settings) -> FetchCache[AnalyzeResponse]:
    global _shared_analysis_cache
    if _shared_analysis_cache is None:
        _shared_analysis_cache = FetchCache(
            ttl_seconds=settings.fetch_cache_ttl_seconds,
            max_total_bytes=settings.fetch_cache_max_mb * 1024 * 1024,
        )
    return _shared_analysis_cache


def _summarize(issues: list[Issue], data_quality: DataQuality) -> str:
    if data_quality == "og_only":
        return _OG_SUMMARY
    if not issues:
        return "No issues found. The page passed all checks."
    highs = sum(1 for issue in issues if issue.severity == "high")
    mediums = sum(1 for issue in issues if issue.severity == "medium")
    lows = len(issues) - highs - mediums
    return (
        f"Found {len(issues)} issues "
        f"({highs} high, {mediums} medium, {lows} low). "
        f"Top fix: {issues[0].title}."
    )


def _response_size(response: AnalyzeResponse) -> int:
    return len(response.model_dump_json().encode("utf-8")) + 256


def _extract_ai_inputs(html: str) -> tuple[str, str]:
    return extract_page_text(html), extract_primary_cta(html)


async def _run_pagespeed_bounded(
    final_url: str,
    settings: Settings,
    cache: FetchCache[PageSpeedAnalysis],
    client: httpx.Client | None,
) -> PageSpeedAnalysis:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                analyze_pagespeed, final_url, settings=settings, client=client, cache=cache
            ),
            PAGESPEED_BUDGET_S,
        )
    except TimeoutError:
        return PageSpeedAnalysis(issues=[], limitations=[_PAGESPEED_TIMEOUT])
    except Exception:
        logger.exception("pagespeed stage failed")
        return PageSpeedAnalysis(issues=[], limitations=["Performance data unavailable"])


def _youtube_page_text(data: YoutubeData) -> str:
    """Frame extracted video data for the AI layer, transcript included."""
    parts = [f"Video title: {data.title or '(missing)'}"]
    parts.append(f"Description: {data.description or '(missing)'}")
    if data.transcript:
        parts.append(f"Transcript excerpt: {data.transcript[:1000]}")
    return "\n\n".join(parts)[:4000]


def _youtube_originals(data: YoutubeData) -> RewriteOriginals:
    description = data.description or ""
    return RewriteOriginals(
        title=data.title or "",
        meta_description=first_description_line(description),
        h1="",
        cta=extract_cta_line(description),
    )


async def _run_ai_bounded(
    issues: list[Issue],
    page_text: str,
    originals: RewriteOriginals,
    brand_voice: str,
    resolved: Settings,
    ai_client: AIClient | None,
) -> AIResult:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                enhance_issues,
                issues,
                page_text=page_text,
                originals=originals,
                brand_voice=brand_voice,
                settings=resolved,
                client=ai_client,
            ),
            AI_BUDGET_S,
        )
    except TimeoutError:
        return AIResult(issues=issues, rewrites=[], limitations=[_AI_TIMEOUT])
    except Exception:
        logger.exception("ai stage failed")
        return AIResult(issues=issues, rewrites=[], limitations=["AI explanations unavailable."])


def _assemble_response(
    request_id: str,
    fetched: FetchedPage,
    quality: DataQuality,
    report: ScoredResult,
    ai_result: AIResult,
) -> AnalyzeResponse:
    return AnalyzeResponse(
        request_id=request_id,
        url=fetched.final_url,
        fetched_at=datetime.now(UTC),
        data_quality=quality,
        summary=_summarize(ai_result.issues, quality),
        issues=ai_result.issues,
        rewrites=ai_result.rewrites,
        limitations=[*report.limitations, *ai_result.limitations],
        score=report.score,
    )


async def _run_pipeline(
    raw_url: str,
    *,
    request_id: str,
    brand_voice: str,
    resolved: Settings,
    store: FetchCache[AnalyzeResponse],
    fetch_cache: FetchCache[FetchedPage],
    pagespeed_cache: FetchCache[PageSpeedAnalysis],
    browser_manager: BrowserManager | None,
    seo_client: httpx.Client | None,
    pagespeed_client: httpx.Client | None,
    youtube_client: httpx.Client | None,
    ai_client: AIClient | None,
) -> AnalyzeResponse:
    prepared = await asyncio.to_thread(prepare_fetch, raw_url, settings=resolved, cache=fetch_cache)
    if isinstance(prepared, FetchedPage):
        hit = store.get(prepared.request_url)
        if hit is not None:
            return hit.model_copy(update={"request_id": request_id})
        fetched = prepared
        cache_key = prepared.request_url
    else:
        cache_key = prepared
        hit = store.get(cache_key)
        if hit is not None:
            return hit.model_copy(update={"request_id": request_id})
        fetched = await fetch_page(
            cache_key, settings=resolved, cache=fetch_cache, browser_manager=browser_manager
        )
    if fetched.data_quality == "og_only":
        response = AnalyzeResponse(
            request_id=request_id,
            url=fetched.final_url,
            fetched_at=datetime.now(UTC),
            data_quality="og_only",
            summary=_OG_SUMMARY,
            issues=[],
            rewrites=[],
            limitations=[_OG_LIMITATION],
            score=None,
        )
        store.set(cache_key, response, _response_size(response))
        return response
    if is_youtube_video_url(fetched.final_url):
        return await _run_youtube_pipeline(
            fetched,
            cache_key,
            request_id=request_id,
            brand_voice=brand_voice,
            resolved=resolved,
            store=store,
            youtube_client=youtube_client,
            ai_client=ai_client,
        )
    seo_task = asyncio.ensure_future(
        asyncio.to_thread(analyze_seo, fetched.html, fetched.final_url, http_client=seo_client)
    )
    pagespeed = await _run_pagespeed_bounded(
        fetched.final_url, resolved, pagespeed_cache, pagespeed_client
    )
    seo = await seo_task
    quality: DataQuality = "full" if not pagespeed.limitations else "partial"
    report = build_report(seo, pagespeed, quality)
    page_text, cta = await asyncio.to_thread(_extract_ai_inputs, fetched.html)
    originals = RewriteOriginals(
        title=fetched.features.title or "",
        meta_description=fetched.features.meta_description or "",
        h1=fetched.features.h1_texts[0] if fetched.features.h1_texts else "",
        cta=cta,
    )
    ai_result = await _run_ai_bounded(
        report.issues, page_text, originals, brand_voice, resolved, ai_client
    )
    response = _assemble_response(request_id, fetched, quality, report, ai_result)
    store.set(cache_key, response, _response_size(response))
    return response


async def _run_youtube_pipeline(
    fetched: FetchedPage,
    cache_key: str,
    *,
    request_id: str,
    brand_voice: str,
    resolved: Settings,
    store: FetchCache[AnalyzeResponse],
    youtube_client: httpx.Client | None,
    ai_client: AIClient | None,
) -> AnalyzeResponse:
    """Analyze a video page with the YouTube checklist only."""
    youtube = await asyncio.to_thread(
        analyze_youtube, fetched.html, fetched.final_url, transcript_client=youtube_client
    )
    quality: DataQuality = "full" if youtube.data.transcript_status != "unknown" else "partial"
    # Web analyzers do not run on video pages; empty shells keep scoring honest.
    seo_shell = SeoAnalysis(issues=[], stats=SeoStats(0, 0, 0, "present", "present"))
    pagespeed_shell = PageSpeedAnalysis(issues=[], limitations=[])
    report = build_report(seo_shell, pagespeed_shell, quality, youtube=youtube)
    ai_result = await _run_ai_bounded(
        report.issues,
        _youtube_page_text(youtube.data),
        _youtube_originals(youtube.data),
        brand_voice,
        resolved,
        ai_client,
    )
    response = _assemble_response(request_id, fetched, quality, report, ai_result)
    store.set(cache_key, response, _response_size(response))
    return response


async def run_analysis(
    raw_url: str,
    *,
    request_id: str,
    brand_voice: str = "",
    settings: Settings | None = None,
    fetch_cache: FetchCache[FetchedPage] | None = None,
    pagespeed_cache: FetchCache[PageSpeedAnalysis] | None = None,
    analysis_cache: FetchCache[AnalyzeResponse] | None = None,
    browser_manager: BrowserManager | None = None,
    seo_client: httpx.Client | None = None,
    pagespeed_client: httpx.Client | None = None,
    youtube_client: httpx.Client | None = None,
    ai_client: AIClient | None = None,
) -> AnalyzeResponse:
    """Validate, fetch, analyze, score, enhance, and cache one URL."""
    resolved = settings or get_settings()
    store = analysis_cache if analysis_cache is not None else _get_shared_analysis_cache(resolved)
    if fetch_cache is not None:
        fetch_store = fetch_cache
    else:
        fetch_store = FetchCache(
            ttl_seconds=resolved.fetch_cache_ttl_seconds,
            max_total_bytes=resolved.fetch_cache_max_mb * 1024 * 1024,
        )
    try:
        async with asyncio.timeout(TOTAL_BUDGET_S):
            return await _run_pipeline(
                raw_url,
                request_id=request_id,
                brand_voice=brand_voice,
                resolved=resolved,
                store=store,
                fetch_cache=fetch_store,
                pagespeed_cache=(
                    pagespeed_cache
                    if pagespeed_cache is not None
                    else FetchCache(ttl_seconds=86400, max_total_bytes=32 * 1024 * 1024)
                ),
                browser_manager=browser_manager,
                seo_client=seo_client,
                pagespeed_client=pagespeed_client,
                youtube_client=youtube_client,
                ai_client=ai_client,
            )
    except TimeoutError:
        raise FetchError("FETCH_TIMEOUT", "Analysis timed out before completing.")
