"""Deterministic creative checks for uploaded images.

Every rule measures pixels or bytes with Pillow: aspect ratio against
the target platform, dimensions, file size, brightness, contrast, and
edge detail. Thresholds are fixed below; the AI layer only explains
these findings afterward and never changes them.
"""

import io
from dataclasses import dataclass
from typing import TypedDict

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

from app.schemas import CreativePlatform, Evidence, Issue, Severity


class PlatformSpec(TypedDict):
    """Public creative guidance per placement: label, ratio, min display size."""

    label: str
    ratio: tuple[int, int]
    min_width: int
    min_height: int


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000
_ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})

# Recommended minimum display size per platform, from each platform's
# public creative guidance. Aspect is width:height. Deviation over 5
# percent means the platform will crop or letterbox the image.
PLATFORM_SPECS: dict[CreativePlatform, PlatformSpec] = {
    "instagram_post": {
        "label": "Instagram post",
        "ratio": (1, 1),
        "min_width": 1080,
        "min_height": 1080,
    },
    "instagram_story": {
        "label": "Instagram story",
        "ratio": (9, 16),
        "min_width": 1080,
        "min_height": 1920,
    },
    "facebook_post": {
        "label": "Facebook post",
        "ratio": (1200, 630),
        "min_width": 1200,
        "min_height": 630,
    },
    "x_post": {
        "label": "X post",
        "ratio": (16, 9),
        "min_width": 1200,
        "min_height": 675,
    },
    "youtube_thumbnail": {
        "label": "YouTube thumbnail",
        "ratio": (16, 9),
        "min_width": 1280,
        "min_height": 720,
    },
}

_HEAVY_BYTES = 2 * 1024 * 1024
_DARK_MEAN = 40.0
_BRIGHT_MEAN = 215.0
_FLAT_CONTRAST = 25.0
_LOW_DETAIL = 0.02


@dataclass(frozen=True)
class ImageStats:
    """Measured facts about an uploaded image. All values are exact."""

    image_format: str
    width: int
    height: int
    byte_size: int
    brightness: float
    contrast: float
    edge_ratio: float


def measure_image(data: bytes) -> ImageStats:
    """Decode bytes and measure pixel facts. Raises ValueError when invalid."""
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("image is larger than 10 MB")
    if not data:
        raise ValueError("image is empty")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            fmt = (image.format or "").upper()
            if fmt not in _ALLOWED_FORMATS:
                raise ValueError("image must be JPEG, PNG, or WebP")
            width, height = image.size
            if width <= 0 or height <= 0:
                raise ValueError("image has no pixels")
            if width * height > MAX_IMAGE_PIXELS:
                raise ValueError("image has too many pixels")
            gray = image.convert("L")
            stats = ImageStat.Stat(gray)
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_stats = ImageStat.Stat(edges)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("file is not a supported image") from exc
    return ImageStats(
        image_format=fmt,
        width=width,
        height=height,
        byte_size=len(data),
        brightness=round(stats.mean[0], 1),
        contrast=round(stats.stddev[0], 1),
        edge_ratio=round(edge_stats.mean[0] / 255.0, 4),
    )


def _issue(
    rule_id: str,
    severity: Severity,
    title: str,
    evidence: str,
    why: str,
    fix: str,
) -> Issue:
    return Issue(
        id=rule_id,
        category="content",
        title=title,
        severity=severity,
        confidence=0.9,
        evidence=Evidence(type="metric", value=evidence),
        source="creative:image",
        why_it_matters=why,
        suggested_fix=fix,
        impact_rank=1,
    )


def _check_aspect(stats: ImageStats, platform: CreativePlatform) -> list[Issue]:
    """Flag when the shape is over 2 percent off the platform ratio."""
    spec = PLATFORM_SPECS[platform]
    ratio = spec["ratio"]
    target = ratio[0] / ratio[1]
    actual = stats.width / stats.height
    deviation = abs(actual - target) / target
    evidence = f"{stats.width}x{stats.height} (ratio {actual:.2f} vs {target:.2f})"
    if deviation > 0.05:
        return [
            _issue(
                "creative-aspect",
                "high",
                f"Wrong shape for {spec['label']}",
                evidence,
                "The platform crops or letterboxes off-ratio images, which can cut text.",
                f"Resize or re-crop to the {ratio[0]}:{ratio[1]} shape before posting.",
            )
        ]
    if deviation > 0.02:
        return [
            _issue(
                "creative-aspect",
                "medium",
                f"Slightly off shape for {spec['label']}",
                evidence,
                "Small ratio differences still trigger automatic cropping on some placements.",
                f"Adjust to exactly {ratio[0]}:{ratio[1]} for a clean fit.",
            )
        ]
    return []


def _check_dimensions(stats: ImageStats, platform: CreativePlatform) -> list[Issue]:
    """Flag when either side is under the recommended display size."""
    spec = PLATFORM_SPECS[platform]
    min_width = spec["min_width"]
    min_height = spec["min_height"]
    if stats.width >= min_width and stats.height >= min_height:
        return []
    return [
        _issue(
            "creative-dimensions",
            "low",
            "Small image for this placement",
            f"{stats.width}x{stats.height} vs recommended {min_width}x{min_height}",
            "Small images are scaled up and look soft on high density screens.",
            "Export at or above the recommended size and re-upload.",
        )
    ]


def _check_file_size(stats: ImageStats) -> list[Issue]:
    """Flag when the file is over 2 MB."""
    if stats.byte_size <= _HEAVY_BYTES:
        return []
    mb = stats.byte_size / (1024 * 1024)
    return [
        _issue(
            "creative-file-size",
            "low",
            "Heavy image file",
            f"{mb:.1f} MB",
            "Heavy files load slowly in feeds and can fail platform upload limits.",
            "Compress to under 2 MB with JPEG quality 80 or WebP.",
        )
    ]


def _check_brightness(stats: ImageStats) -> list[Issue]:
    """Flag when mean brightness is under 40 or over 215."""
    if stats.brightness < _DARK_MEAN:
        return [
            _issue(
                "creative-brightness",
                "low",
                "Image looks very dark",
                f"mean brightness {stats.brightness}",
                "Dark images lose detail on dim phone screens.",
                "Lift exposure until the subject reads clearly at thumbnail size.",
            )
        ]
    if stats.brightness > _BRIGHT_MEAN:
        return [
            _issue(
                "creative-brightness",
                "low",
                "Image looks washed out",
                f"mean brightness {stats.brightness}",
                "Overbright images lose contrast and text placed on them is hard to read.",
                "Pull exposure down and check that white areas still hold detail.",
            )
        ]
    return []


def _check_contrast(stats: ImageStats) -> list[Issue]:
    """Flag when brightness spread is under 25."""
    if stats.contrast >= _FLAT_CONTRAST:
        return []
    return [
        _issue(
            "creative-contrast",
            "low",
            "Image looks flat",
            f"brightness spread {stats.contrast}",
            "Flat images blend into the feed and get less attention.",
            "Add contrast between subject and background, then re-check.",
        )
    ]


def _check_detail(stats: ImageStats) -> list[Issue]:
    """Flag when edge density is under 2 percent."""
    if stats.edge_ratio >= _LOW_DETAIL:
        return []
    return [
        _issue(
            "creative-detail",
            "low",
            "Image has little visible detail",
            f"edge density {stats.edge_ratio:.3f}",
            "Low detail reads as blurry or blank at small sizes.",
            "Use a sharper photo or add clear foreground shapes and text.",
        )
    ]


def analyze_image(stats: ImageStats, platform: CreativePlatform) -> list[Issue]:
    """Run every image rule. Order is stable; ranking happens later."""
    issues: list[Issue] = []
    issues.extend(_check_aspect(stats, platform))
    issues.extend(_check_dimensions(stats, platform))
    issues.extend(_check_file_size(stats))
    issues.extend(_check_brightness(stats))
    issues.extend(_check_contrast(stats))
    issues.extend(_check_detail(stats))
    return issues


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    width: int,
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_improved(data: bytes, headline: str, subtext: str, cta: str) -> bytes:
    """Draw headline, subtext, and CTA as real text overlays on the image.

    Layout is fixed: a top band for the headline and a bottom band for
    the subtext plus CTA box. Returns PNG bytes at the original size.
    """
    stats = measure_image(data)
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        canvas = image.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas, "RGBA")
    margin = max(16, stats.width // 24)
    top_h = max(64, stats.height // 5)
    bottom_h = max(80, stats.height // 4)
    draw.rectangle([0, 0, stats.width, top_h], fill=(0, 0, 0, 170))
    draw.rectangle([0, stats.height - bottom_h, stats.width, stats.height], fill=(0, 0, 0, 170))
    head_font = _load_font(max(20, stats.width // 22))
    body_font = _load_font(max(16, stats.width // 34))
    usable = stats.width - margin * 2
    lines = _wrap(draw, headline.strip(), head_font, usable)
    y = float(margin)
    for line in lines[:3]:
        draw.text((margin, y), line, font=head_font, fill=(255, 255, 255, 255))
        box = draw.textbbox((margin, y), line, font=head_font)
        y = box[3] + 4
    y = float(stats.height - bottom_h + margin // 2)
    if subtext.strip():
        for line in _wrap(draw, subtext.strip(), body_font, usable)[:2]:
            draw.text((margin, y), line, font=body_font, fill=(255, 255, 255, 255))
            box = draw.textbbox((margin, y), line, font=body_font)
            y = box[3] + 4
    if cta.strip():
        label = cta.strip()
        pad = max(10, stats.width // 80)
        box = draw.textbbox((0, 0), label, font=body_font)
        text_w = box[2] - box[0]
        text_h = box[3] - box[1]
        x0, y0 = margin, y + 4
        draw.rectangle(
            [x0, y0, x0 + text_w + pad * 2, y0 + text_h + pad * 2],
            outline=(255, 255, 255, 255),
            width=max(2, stats.width // 400),
        )
        draw.text((x0 + pad, y0 + pad), label, font=body_font, fill=(255, 255, 255, 255))
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()
