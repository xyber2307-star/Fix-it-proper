"""Strict Pydantic shapes for Groq JSON output."""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import RewriteTarget


class ExplanationItem(BaseModel):
    """One explanation pair the model returns for a known issue id."""

    model_config = ConfigDict(extra="forbid")

    issue_id: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1, max_length=1000)
    suggested_fix: str = Field(min_length=1, max_length=1000)


class ExplanationsResponse(BaseModel):
    """Task 1 output: explanations for the top issues."""

    model_config = ConfigDict(extra="forbid")

    explanations: list[ExplanationItem] = Field(min_length=1)


class RewriteItem(BaseModel):
    """One rewrite target with 2 to 3 variants."""

    model_config = ConfigDict(extra="forbid")

    target: RewriteTarget
    variants: list[str] = Field(min_length=2, max_length=3)


class RewritesResponse(BaseModel):
    """Task 2 output: rewrite variants per target."""

    model_config = ConfigDict(extra="forbid")

    rewrites: list[RewriteItem] = Field(min_length=1)
