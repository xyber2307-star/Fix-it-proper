"""Tests for Creative Review: image rules, overlays, review, endpoints."""

import io
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.ai.creative import FAILED as CREATIVE_FAILED
from app.ai.creative import NO_KEY as CREATIVE_NO_KEY
from app.ai.creative import review_creative
from app.analyzers import creative as creative_analyzer
from app.analyzers.creative import PLATFORM_SPECS, analyze_image, measure_image, render_improved
from app.config import Settings
from app.db import AuthError, VerifiedUser
from app.main import create_app
from app.schemas import Evidence, Issue
from tests.conftest import emulator_settings, offline_settings

GOOD_TOKEN = "good-token"


def _png(width: int, height: int, color: tuple[int, int, int] = (120, 130, 140)) -> bytes:
    image = Image.new("RGB", (width, height), color)
    pixels = image.load()
    assert pixels is not None
    for x in range(0, width, 4):
        for y in range(0, height, 4):
            pixels[x, y] = (20, 20, 20)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _flat_png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_platform_specs_cover_five_placements():
    assert set(PLATFORM_SPECS) == {
        "instagram_post",
        "instagram_story",
        "facebook_post",
        "x_post",
        "youtube_thumbnail",
    }


def test_measure_rejects_non_image():
    with pytest.raises(ValueError, match="not a supported image"):
        measure_image(b"this is not an image")


def test_measure_rejects_oversize():
    with pytest.raises(ValueError, match="10 MB"):
        measure_image(b"\x89PNG" + b"\x00" * creative_analyzer.MAX_IMAGE_BYTES)


def test_measure_reads_exact_facts():
    stats = measure_image(_png(600, 600))
    assert stats.image_format == "PNG"
    assert (stats.width, stats.height) == (600, 600)
    assert stats.byte_size > 0
    assert 0 <= stats.brightness <= 255


def test_aspect_rule_flags_wrong_shape_high():
    stats = measure_image(_png(1200, 600))
    issues = analyze_image(stats, "instagram_post")
    aspect = [issue for issue in issues if issue.id == "creative-aspect"]
    assert len(aspect) == 1
    assert aspect[0].severity == "high"
    assert "1.00" in aspect[0].evidence.value or "1:1" in aspect[0].suggested_fix


def test_aspect_rule_passes_correct_shape():
    stats = measure_image(_png(1080, 1080))
    issues = analyze_image(stats, "instagram_post")
    assert [issue for issue in issues if issue.id == "creative-aspect"] == []


def test_dimensions_rule_flags_small_image():
    stats = measure_image(_png(400, 400))
    issues = analyze_image(stats, "instagram_post")
    dims = [issue for issue in issues if issue.id == "creative-dimensions"]
    assert len(dims) == 1
    assert dims[0].severity == "low"


def test_brightness_rule_flags_dark_image():
    stats = measure_image(_flat_png(500, 500, (10, 10, 10)))
    issues = analyze_image(stats, "instagram_post")
    dark = [issue for issue in issues if issue.id == "creative-brightness"]
    assert len(dark) == 1
    assert "dark" in dark[0].title


def test_contrast_and_detail_flag_flat_image():
    stats = measure_image(_flat_png(500, 500, (128, 128, 128)))
    ids = {issue.id for issue in analyze_image(stats, "instagram_post")}
    assert "creative-contrast" in ids
    assert "creative-detail" in ids


def test_render_improved_returns_png_with_overlays():
    before = _png(800, 800)
    after = render_improved(before, "Spring sale ends Friday", "Half price callouts", "Shop now")
    assert after[:8] == b"\x89PNG\r\n\x1a\n"
    with Image.open(io.BytesIO(after)) as image:
        assert image.size == (800, 800)
    with Image.open(io.BytesIO(before)) as original:
        assert after != before
        assert len(after) > 0
        assert original.size == (800, 800)


def test_render_improved_changes_top_band_pixels():
    before = _flat_png(600, 600, (200, 200, 200))
    after = render_improved(before, "Hello world", "", "")
    with Image.open(io.BytesIO(after)) as image:
        pixels = image.load()
        assert pixels is not None
        assert pixels[300, 10] != (200, 200, 200)


class _FakeClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls = 0

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls += 1
        assert "Placement" in user
        return self.payload


def test_review_returns_none_without_key():
    settings = Settings(log_level="WARNING", groq_api_key="")
    review, limitation = review_creative(
        [],
        platform_label="Instagram post",
        goal="",
        observations="",
        settings=settings,
        client=_FakeClient({}),
    )
    assert review is None
    assert limitation == CREATIVE_NO_KEY


def test_review_validates_model_output():
    settings = Settings(log_level="WARNING", groq_api_key="key")
    payload = {
        "summary": "Crop to a square and brighten the subject.",
        "changes": ["Crop to 1:1.", "Raise brightness."],
        "suggested_headline": "Spring sale ends Friday",
        "suggested_subtext": "Half price callouts this week",
        "suggested_cta": "Shop now",
    }
    review, limitation = review_creative(
        [],
        platform_label="Instagram post",
        goal="sales",
        observations="PNG 1200x600.",
        settings=settings,
        client=_FakeClient(payload),
    )
    assert limitation is None
    assert review is not None
    assert review.label == "AI generated, test before using"
    assert review.changes == ["Crop to 1:1.", "Raise brightness."]


def test_review_rejects_bad_output():
    settings = Settings(log_level="WARNING", groq_api_key="key")
    review, limitation = review_creative(
        [],
        platform_label="Instagram post",
        goal="",
        observations="",
        settings=settings,
        client=_FakeClient({"wrong": True}),
    )
    assert review is None
    assert limitation == CREATIVE_FAILED


@pytest.fixture
def offline_client():
    return TestClient(create_app(offline_settings()))


@pytest.fixture
def authed_client(monkeypatch, require_emulator, require_loop):
    async def fake_verify(app: Any, token: str) -> VerifiedUser:
        if token == GOOD_TOKEN:
            return VerifiedUser(uid="creative-user-1", email="creative-user-1@example.com")
        raise AuthError("bad token")

    monkeypatch.setattr("app.main.verify_id_token", fake_verify)
    return TestClient(create_app(emulator_settings()))


def test_creative_endpoints_need_auth(offline_client):
    assert offline_client.post("/api/creative/analyze").status_code == 401
    assert offline_client.post("/api/creative/improve").status_code == 401


def test_creative_analyze_needs_exactly_one_source(authed_client, monkeypatch):
    headers = {"Authorization": f"Bearer {GOOD_TOKEN}"}
    monkeypatch.setattr(
        "app.main.review_creative", lambda *a, **k: (None, "AI review unavailable.")
    )
    both = authed_client.post(
        "/api/creative/analyze",
        data={
            "platform": "instagram_post",
            "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        },
        files={"image": ("a.png", _png(200, 200), "image/png")},
        headers=headers,
    )
    assert both.status_code == 422
    neither = authed_client.post(
        "/api/creative/analyze",
        data={"platform": "instagram_post"},
        headers=headers,
    )
    assert neither.status_code == 422


def test_creative_analyze_image_path(authed_client, monkeypatch):
    headers = {"Authorization": f"Bearer {GOOD_TOKEN}"}
    monkeypatch.setattr(
        "app.main.review_creative", lambda *a, **k: (None, "AI review unavailable.")
    )
    response = authed_client.post(
        "/api/creative/analyze",
        data={"platform": "instagram_post", "goal": "Get spring bookings."},
        files={"image": ("square.png", _png(1080, 1080), "image/png")},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "image"
    assert body["platform"] == "instagram_post"
    assert body["data_quality"] == "full"
    assert body["review"] is None
    assert "AI review unavailable." in body["limitations"]
    ranks = [issue["impact_rank"] for issue in body["issues"]]
    assert ranks == sorted(ranks)
    assert all(issue["source"] == "creative:image" for issue in body["issues"])


def test_creative_analyze_rejects_bad_platform(authed_client):
    headers = {"Authorization": f"Bearer {GOOD_TOKEN}"}
    response = authed_client.post(
        "/api/creative/analyze",
        data={"platform": "myspace"},
        files={"image": ("a.png", _png(200, 200), "image/png")},
        headers=headers,
    )
    assert response.status_code == 422


def test_creative_improve_returns_png(authed_client):
    headers = {"Authorization": f"Bearer {GOOD_TOKEN}"}
    response = authed_client.post(
        "/api/creative/improve",
        data={"headline": "Spring sale", "subtext": "Ends Friday", "cta": "Shop now"},
        files={"image": ("a.png", _png(640, 640), "image/png")},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_creative_improve_needs_headline(authed_client):
    headers = {"Authorization": f"Bearer {GOOD_TOKEN}"}
    response = authed_client.post(
        "/api/creative/improve",
        data={"headline": "  "},
        files={"image": ("a.png", _png(640, 640), "image/png")},
        headers=headers,
    )
    assert response.status_code == 422


def test_creative_review_never_decides_findings():
    issue = Issue(
        id="creative-aspect",
        category="content",
        title="Wrong shape",
        severity="high",
        confidence=0.9,
        evidence=Evidence(type="metric", value="1200x600"),
        source="creative:image",
        why_it_matters="why",
        suggested_fix="fix",
        impact_rank=1,
    )
    settings = Settings(log_level="WARNING", groq_api_key="key")
    payload = {
        "summary": "Fix the shape.",
        "changes": ["Crop to 1:1."],
        "suggested_headline": "Sale",
        "suggested_subtext": "",
        "suggested_cta": "",
    }
    review_creative(
        [issue],
        platform_label="Instagram post",
        goal="",
        observations="",
        settings=settings,
        client=_FakeClient(payload),
    )
    assert (issue.severity, issue.impact_rank, issue.evidence.value) == (
        "high",
        1,
        "1200x600",
    )
