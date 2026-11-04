"""AI review for Creative Review. Runs only after deterministic checks finish.

Input is the ranked issue list plus platform and goal text. The model
explains changes and drafts overlay texts; it never decides findings.
"""

import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai.client import AIClient, AIError, GroqClient
from app.brand import SLUG
from app.config import Settings, get_settings
from app.schemas import CreativeReview, Issue

logger = logging.getLogger(f"{SLUG}.ai.creative")

NO_KEY = "AI review unavailable (no API key configured)."
FAILED = "AI review unavailable (the model output failed validation)."


class _ReviewResponse(BaseModel):
    """Task output: summary, ranked changes, and overlay text drafts."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=600)
    changes: list[str] = Field(min_length=1, max_length=6)
    suggested_headline: str = Field(min_length=1, max_length=90)
    suggested_subtext: str = Field(min_length=0, max_length=140)
    suggested_cta: str = Field(min_length=0, max_length=40)


_SYSTEM = (
    "You review one ad creative for a small business owner. "
    "Write plain, specific sentences. Do not invent claims, prices, "
    "awards, or statistics. Do not use superlatives like best or "
    "number one. Reply with JSON only."
)


def _user_prompt(issues: list[Issue], platform_label: str, goal: str, observations: str) -> str:
    lines = [
        f"Placement: {platform_label}.",
        f"Advertiser goal: {goal or '(not stated)'}.",
        f"Measured observations: {observations or '(none)'}",
        "Ranked findings from deterministic checks (severity, title, evidence):",
    ]
    for issue in issues[:10]:
        lines.append(
            f"- [{issue.severity}] {issue.title}: {issue.evidence.value} "
            f"Suggested fix: {issue.suggested_fix}"
        )
    lines.append(
        "Return JSON with keys summary (1 to 2 sentences), changes "
        "(array of 1 to 6 strings, most important first), "
        "suggested_headline (max 90 chars), suggested_subtext "
        "(max 140 chars, may be empty), suggested_cta (max 40 chars, "
        "may be empty, for example Shop now)."
    )
    return "\n".join(lines)


def review_creative(
    issues: list[Issue],
    *,
    platform_label: str,
    goal: str,
    observations: str,
    settings: Settings | None = None,
    client: AIClient | None = None,
) -> tuple[CreativeReview | None, str | None]:
    """Draft the AI review. Returns (review, None) or (None, limitation)."""
    resolved = settings or get_settings()
    if not (resolved.groq_api_key or "").strip():
        return None, NO_KEY
    active = (
        client
        if client is not None
        else GroqClient(api_key=resolved.groq_api_key, model=resolved.groq_model)
    )
    user = _user_prompt(issues, platform_label, goal, observations)
    last_error = ""
    for _ in range(2):
        try:
            payload = active.complete_json(_SYSTEM, user)
            parsed = _ReviewResponse.model_validate(payload)
        except AIError as exc:
            logger.info("creative review fallback", extra={"reason": exc.kind})
            return None, FAILED
        except ValidationError:
            last_error = "validation"
            continue
        return (
            CreativeReview(
                label="AI generated, test before using",
                summary=parsed.summary,
                changes=parsed.changes,
                suggested_headline=parsed.suggested_headline,
                suggested_subtext=parsed.suggested_subtext,
                suggested_cta=parsed.suggested_cta,
            ),
            None,
        )
    logger.info("creative review fallback", extra={"reason": last_error})
    return None, FAILED
