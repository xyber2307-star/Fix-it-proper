"""AI enhancement layer. Runs only after deterministic checks finish.

Inputs are ranked issues, extracted page text, and pre-extracted
originals. This module never parses raw HTML and never applies
anything. Severity, rank, and evidence pass through untouched.
"""

import logging
import re
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.client import AIClient, AIError, GroqClient
from app.ai.models import ExplanationsResponse, RewritesResponse
from app.ai.prompts import (
    SUPERLATIVES,
    build_explanations_prompt,
    build_rewrites_prompt,
)
from app.brand import SLUG
from app.config import Settings, get_settings
from app.schemas import Issue, Rewrite, RewriteTarget

logger = logging.getLogger(f"{SLUG}.ai")

_M = TypeVar("_M", bound=BaseModel)

_NO_KEY = "AI explanations and rewrites unavailable (no API key configured)."
_FAILED = "AI output failed validation; showing deterministic text with no rewrites."
_NO_CONTENT = "Rewrites unavailable (page content missing)."
_NO_SURVIVORS = "AI rewrites unavailable (no variants passed quality checks)."

_BOUNDS: dict[str, tuple[int, int]] = {
    "title": (30, 60),
    "meta_description": (70, 160),
    "h1": (1, 200),
    "cta": (1, 120),
}
_TARGET_ORDER: tuple[RewriteTarget, ...] = ("title", "meta_description", "h1", "cta")
_CURRENCY = frozenset({"$", "€", "£"})
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_SUPERLATIVE_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(word) for word in sorted(SUPERLATIVES)) + r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RewriteOriginals:
    """Current copy per rewrite target, extracted by deterministic code."""

    title: str
    meta_description: str
    h1: str
    cta: str


@dataclass(frozen=True)
class AIResult:
    """Issues with AI explanations merged plus labeled rewrites."""

    issues: list[Issue]
    rewrites: list[Rewrite]
    limitations: list[str]


def _complete_validated(client: AIClient, system: str, user: str, model: type[_M]) -> _M:
    """Call once, retrying a single time when the model output is bad."""
    for attempt in (0, 1):
        try:
            payload = client.complete_json(system, user)
        except AIError as exc:
            if exc.kind in ("timeout", "transport") or attempt == 1:
                raise
            continue
        try:
            return model.model_validate(payload)
        except ValidationError:
            if attempt == 1:
                raise
    raise AIError("transport")  # unreachable: the loop always returns or raises


def _take_sentences(text: str, limit: int = 2) -> str:
    parts = [part.strip() for part in _SENTENCE_END.split(text.strip()) if part.strip()]
    return " ".join(parts[:limit])


def _has_superlative(text: str) -> bool:
    return _SUPERLATIVE_PATTERN.search(text) is not None


def _has_new_claim_marker(text: str, original: str) -> bool:
    for marker in (*_CURRENCY, "%"):
        if marker in text and marker not in original:
            return True
    return False


def _clean_variants(original: str, variants: list[str], *, min_len: int, max_len: int) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        text = " ".join(variant.split())
        if not (min_len <= len(text) <= max_len):
            continue
        if _has_superlative(text):
            continue
        if _has_new_claim_marker(text, original):
            continue
        key = text.casefold()
        if key in seen or key == original.casefold():
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned[:3]


def _merge_explanations(
    issues: list[Issue], top_ids: set[str], explanations: dict[str, tuple[str, str]]
) -> list[Issue]:
    merged: list[Issue] = []
    for issue in issues:
        if issue.id not in top_ids or issue.id not in explanations:
            merged.append(issue)
            continue
        why, fix = explanations[issue.id]
        merged.append(
            issue.model_copy(
                update={
                    "why_it_matters": _take_sentences(why),
                    "suggested_fix": _take_sentences(fix),
                }
            )
        )
    return merged


def _originals_map(originals: RewriteOriginals) -> dict[str, str]:
    return {
        "title": originals.title.strip(),
        "meta_description": originals.meta_description.strip(),
        "h1": originals.h1.strip(),
        "cta": originals.cta.strip(),
    }


def enhance_issues(
    issues: list[Issue],
    *,
    page_text: str,
    originals: RewriteOriginals | None = None,
    brand_voice: str = "",
    settings: Settings | None = None,
    client: AIClient | None = None,
) -> AIResult:
    """Add AI explanations to the top 5 issues and build rewrites.

    Either task failing twice falls back to the deterministic issues
    with no rewrites.
    """
    resolved = settings or get_settings()
    if not (resolved.groq_api_key or "").strip():
        logger.info("ai skipped", extra={"reason": "no-key"})
        return AIResult(issues=list(issues), rewrites=[], limitations=[_NO_KEY])
    active = (
        client
        if client is not None
        else GroqClient(api_key=resolved.groq_api_key, model=resolved.groq_model)
    )
    top_five = issues[:5]
    explanations: dict[str, tuple[str, str]] = {}
    try:
        if top_five:
            system, user = build_explanations_prompt(top_five, page_text, brand_voice)
            parsed = _complete_validated(active, system, user, ExplanationsResponse)
            explanations = {
                item.issue_id: (item.why_it_matters, item.suggested_fix)
                for item in parsed.explanations
            }
        targets = _originals_map(originals) if originals is not None else {}
        targets = {key: value for key, value in targets.items() if value}
        rewrites: list[Rewrite] = []
        rewrites_skipped = originals is None or not targets
        if targets:
            system, user = build_rewrites_prompt(targets, page_text, brand_voice)
            parsed_rewrites = _complete_validated(active, system, user, RewritesResponse)
            by_target = {item.target: item.variants for item in parsed_rewrites.rewrites}
            for target in _TARGET_ORDER:
                if target not in targets or target not in by_target:
                    continue
                min_len, max_len = _BOUNDS[target]
                cleaned = _clean_variants(
                    targets[target], by_target[target], min_len=min_len, max_len=max_len
                )
                if len(cleaned) < 2:
                    continue
                rewrites.append(
                    Rewrite(
                        target=target,
                        original=targets[target],
                        variants=cleaned,
                        label="AI generated, test before using",
                    )
                )
    except (AIError, ValidationError) as exc:
        reason = exc.kind if isinstance(exc, AIError) else "validation"
        logger.info("ai fallback", extra={"reason": reason})
        return AIResult(issues=list(issues), rewrites=[], limitations=[_FAILED])
    merged = _merge_explanations(issues, {issue.id for issue in top_five}, explanations)
    limitations: list[str] = []
    if rewrites_skipped:
        limitations.append(_NO_CONTENT)
    elif originals is not None and not rewrites:
        limitations.append(_NO_SURVIVORS)
    logger.info("ai enhance ok")
    return AIResult(issues=merged, rewrites=rewrites, limitations=limitations)
