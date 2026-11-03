"""Prompt builders for the two AI tasks. Pure functions only."""

from app.schemas import Issue

PAGE_TEXT_LIMIT = 4000
BRAND_VOICE_LIMIT = 500

# Whole words the variant filter drops. Mirrored into the rewrite prompt.
SUPERLATIVES = frozenset(
    {
        "best",
        "greatest",
        "cheapest",
        "fastest",
        "ultimate",
        "perfect",
        "guaranteed",
        "world-class",
        "world class",
        "number one",
        "number 1",
    }
)

EXPLANATIONS_SYSTEM = (
    "You are a website copy editor. Rewrite explanations in plain English "
    "for a small business owner. Use one or two short sentences per field. "
    "Never invent facts, numbers, or claims. Reply with JSON only, no other text."
)

REWRITES_SYSTEM = (
    "You are a website copy editor writing headline variants. Reply with JSON only, no other text."
)


def _brand_block(brand_voice: str) -> str:
    voice = " ".join(brand_voice.split())
    if not voice:
        return ""
    return f"\nBrand voice to match: {voice[:BRAND_VOICE_LIMIT]}"


def build_explanations_prompt(
    issues: list[Issue], page_text: str, brand_voice: str = ""
) -> tuple[str, str]:
    """Build the Task 1 prompt from ranked issues and page text."""
    lines = [
        "Rewrite the explanation fields for these website issues.",
        "Keep each why_it_matters and suggested_fix to one or two sentences.",
        "Use only the issue ids below. Reply with this JSON shape:",
        '{"explanations": [{"issue_id": "...", "why_it_matters": "...", "suggested_fix": "..."}]}',
    ]
    for issue in issues:
        lines.append(
            f"- {issue.id} [{issue.severity}] {issue.title}. "
            f"Evidence: {issue.evidence.value}. "
            f"Current why: {issue.why_it_matters} Current fix: {issue.suggested_fix}"
        )
    text = " ".join(page_text.split())
    if text:
        lines.append(f"Page text for context: {text[:PAGE_TEXT_LIMIT]}")
    lines.append(_brand_block(brand_voice).strip() or "No brand voice given.")
    return EXPLANATIONS_SYSTEM, "\n".join(line for line in lines if line)


def build_rewrites_prompt(
    originals: dict[str, str], page_text: str, brand_voice: str = ""
) -> tuple[str, str]:
    """Build the Task 2 prompt from original copy plus bounds."""
    bounds = {
        "title": "30 to 60 characters",
        "meta_description": "70 to 160 characters",
        "h1": "at most 200 characters",
        "cta": "at most 120 characters",
    }
    lines = [
        "Write 2 to 3 distinct variants for each target below.",
        "Keep the business name and location when the original has them.",
        "Do not invent claims, prices, awards, or statistics.",
        "Do not add prices or percentages the original does not have.",
        f"Avoid superlatives: {', '.join(sorted(SUPERLATIVES))}.",
        "Reply with this JSON shape:",
        '{"rewrites": [{"target": "title", "variants": ["...", "..."]}]}',
    ]
    for target, original in originals.items():
        lines.append(f"- {target} ({bounds[target]}): {original}")
    text = " ".join(page_text.split())
    if text:
        lines.append(f"Page text for context: {text[:PAGE_TEXT_LIMIT]}")
    lines.append(_brand_block(brand_voice).strip() or "No brand voice given.")
    return REWRITES_SYSTEM, "\n".join(line for line in lines if line)
