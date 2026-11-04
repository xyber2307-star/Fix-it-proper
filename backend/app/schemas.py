"""Fix It Proper API contract, single source of truth for backend validation."""

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

DataQuality = Literal["full", "partial", "og_only"]
IssueCategory = Literal["seo", "content", "technical", "performance", "accessibility"]
Severity = Literal["high", "medium", "low"]
EvidenceType = Literal["text", "selector", "metric"]
RewriteTarget = Literal["title", "meta_description", "h1", "cta"]
RewriteLabel = Literal["AI generated, test before using"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyzeRequest(StrictModel):
    url: HttpUrl


class Evidence(StrictModel):
    type: EvidenceType
    value: str


class Issue(StrictModel):
    id: str
    category: IssueCategory
    title: str
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    evidence: Evidence
    source: str
    why_it_matters: str
    suggested_fix: str
    impact_rank: int = Field(ge=1)


class Rewrite(StrictModel):
    target: RewriteTarget
    original: str
    variants: list[str] = Field(min_length=2, max_length=3)
    label: RewriteLabel


class ScoreComponent(StrictModel):
    name: str
    value: float
    weight: float = Field(ge=0, le=1)


class Score(StrictModel):
    value: float = Field(ge=0, le=100)
    formula_version: str
    components: list[ScoreComponent]


class AnalyzeResponse(StrictModel):
    request_id: str
    url: str
    fetched_at: datetime
    data_quality: DataQuality
    summary: str
    issues: list[Issue]
    rewrites: list[Rewrite]
    limitations: list[str]
    score: Score | None = None


class ErrorResponse(StrictModel):
    code: str
    message: str
    retryable: bool


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class ContactRequest(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    message: str = Field(min_length=10, max_length=2000)
    company: str = Field(default="", max_length=200)

    @field_validator("name", "email", "message", "company", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("email")
    @classmethod
    def _email_shape(cls, value: str) -> str:
        if not _EMAIL_RE.match(value):
            raise ValueError("email must look like name@example.com")
        return value


class StatusResponse(StrictModel):
    status: str


class ReportSummary(StrictModel):
    id: str
    url: str
    data_quality: DataQuality
    summary: str
    issue_count: int = Field(ge=0)
    score_value: float | None = Field(default=None, ge=0, le=100)
    created_at: datetime


class ReportListResponse(StrictModel):
    reports: list[ReportSummary]


BusinessSize = Literal["Just me", "2 to 10", "11 to 50", "51 to 200", "Over 200"]


class BusinessProfile(StrictModel):
    """Onboarding profile. Required fields are always present; optionals default empty."""

    business_name: str = Field(min_length=2, max_length=120)
    website: str = Field(min_length=4, max_length=500)
    industry: str = Field(min_length=2, max_length=80)
    city: str = Field(min_length=2, max_length=80)
    country: str = Field(min_length=2, max_length=80)
    size: BusinessSize
    role: str = Field(min_length=2, max_length=80)
    usage_plan: str = Field(default="", max_length=500)
    profession: str = Field(default="", max_length=120)
    referral_source: str = Field(default="", max_length=120)
    help_feedback: str = Field(default="", max_length=1000)

    @field_validator(
        "business_name",
        "website",
        "industry",
        "city",
        "country",
        "role",
        "usage_plan",
        "profession",
        "referral_source",
        "help_feedback",
        mode="before",
    )
    @classmethod
    def _strip(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("website")
    @classmethod
    def _website_must_be_http(cls, value: str) -> str:
        candidate = value if "://" in value else f"https://{value}"
        lowered = candidate.lower()
        if not (lowered.startswith("http://") or lowered.startswith("https://")):
            raise ValueError("website must start with http:// or https://")
        host = candidate.split("://", 1)[1].split("/", 1)[0]
        if "." not in host or " " in host:
            raise ValueError("website must include a domain name")
        return candidate


class ProfileResponse(StrictModel):
    profile: BusinessProfile | None
    profile_complete: bool


CreativeSource = Literal["image", "youtube"]
CreativePlatform = Literal[
    "instagram_post", "instagram_story", "facebook_post", "x_post", "youtube_thumbnail"
]


class CreativeReview(StrictModel):
    """AI review output. Deterministic checks run first; this only explains."""

    label: RewriteLabel
    summary: str
    changes: list[str] = Field(min_length=1, max_length=6)
    suggested_headline: str
    suggested_subtext: str
    suggested_cta: str


class CreativeResponse(StrictModel):
    request_id: str
    source: CreativeSource
    platform: CreativePlatform
    goal: str
    data_quality: DataQuality
    summary: str
    issues: list[Issue]
    review: CreativeReview | None
    limitations: list[str]
