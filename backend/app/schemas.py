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
