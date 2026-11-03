"""Validate API contract fixtures against Pydantic schemas."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas import AnalyzeRequest, AnalyzeResponse, ErrorResponse

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    with open(FIXTURES / name, encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
        return data


def test_full_success_fixture() -> None:
    data = load_fixture("full_success.json")
    parsed = AnalyzeResponse.model_validate(data)
    assert parsed.data_quality == "full"
    assert parsed.limitations == []
    assert parsed.score is not None
    assert len(parsed.issues) == 2
    assert parsed.issues[0].impact_rank == 1


def test_partial_fixture() -> None:
    data = load_fixture("partial.json")
    parsed = AnalyzeResponse.model_validate(data)
    assert parsed.data_quality == "partial"
    assert len(parsed.limitations) == 1
    assert parsed.score is not None


def test_og_only_fixture() -> None:
    data = load_fixture("og_only.json")
    parsed = AnalyzeResponse.model_validate(data)
    assert parsed.data_quality == "og_only"
    assert parsed.issues == []
    assert parsed.rewrites == []
    assert parsed.score is None
    assert len(parsed.limitations) == 2


def test_fetch_blocked_fixture() -> None:
    data = load_fixture("fetch_blocked.json")
    parsed = ErrorResponse.model_validate(data)
    assert parsed.code == "FETCH_BLOCKED"
    assert parsed.retryable is False


def test_invalid_url_fixture() -> None:
    data = load_fixture("invalid_url.json")
    parsed = ErrorResponse.model_validate(data)
    assert parsed.code == "INVALID_URL"
    assert parsed.retryable is False


@pytest.mark.parametrize("url", ["https://example.com", "http://example.com/page?q=1"])
def test_analyze_request_accepts_http_https(url: str) -> None:
    parsed = AnalyzeRequest.model_validate({"url": url})
    assert str(parsed.url).startswith("http")


@pytest.mark.parametrize("url", ["ftp://example.com", "not-a-url", "", "example.com"])
def test_analyze_request_rejects_non_http(url: str) -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate({"url": url})


def test_response_rejects_extra_fields() -> None:
    data = load_fixture("full_success.json")
    data["unexpected"] = "nope"
    with pytest.raises(ValidationError):
        AnalyzeResponse.model_validate(data)
