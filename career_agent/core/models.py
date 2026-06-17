"""Core data contracts for the career-agent pipeline."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SignalType = Literal["news", "market", "social", "weekly_summary", "other"]
OpportunitySource = Literal[
    "career_page",
    "linkedin_email",
    "linkedin_search",
    "manual",
    "demo",
]
RecommendedAction = Literal["apply_now", "review", "skip"]
DocumentType = Literal["resume", "cover_letter", "digest", "preview"]


def _normalize_key_part(value: str) -> str:
    """Normalize text for stable deduplication keys."""
    value = value.strip().lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def _hash_key(*parts: str) -> str:
    """Create a short stable hash from normalized text parts."""
    joined = "|".join(_normalize_key_part(part) for part in parts if part)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


class Signal(BaseModel):
    """A career-relevant signal such as an article, market item, or post."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    title: str = Field(min_length=1)
    signal_type: SignalType = "news"
    url: str | None = None
    category: str | None = None
    summary: str | None = None
    raw_text: str | None = None
    published_at: datetime | None = None
    relevance_score: int | None = Field(default=None, ge=0, le=10)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def dedup_key(self) -> str:
        """Stable identity key, URL-first when available."""
        if self.url:
            return f"signal:url:{_normalize_key_part(self.url)}"
        return f"signal:hash:{_hash_key(self.source, self.title)}"


class FitScore(BaseModel):
    """Structured fit score for a career opportunity."""

    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0, le=100)
    recommended_action: RecommendedAction
    skills_match: int | None = Field(default=None, ge=0, le=25)
    experience_relevance: int | None = Field(default=None, ge=0, le=25)
    geography_match: int | None = Field(default=None, ge=0, le=15)
    org_type_match: int | None = Field(default=None, ge=0, le=15)
    level_match: int | None = Field(default=None, ge=0, le=10)
    background_fit: int | None = Field(default=None, ge=0, le=10)
    match_summary: str = ""
    top_reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    resume_angle: str = ""

    @model_validator(mode="after")
    def action_matches_score_band(self) -> "FitScore":
        """Keep the action broadly aligned with the numeric score."""
        if self.total >= 80 and self.recommended_action not in {"apply_now", "review"}:
            raise ValueError("scores >= 80 should recommend apply_now or review")
        if self.total < 60 and self.recommended_action == "apply_now":
            raise ValueError("scores below 60 cannot recommend apply_now")
        return self


class Opportunity(BaseModel):
    """A job, fellowship, internship, or application target."""

    model_config = ConfigDict(extra="forbid")

    source: OpportunitySource
    source_detail: str | None = None
    job_title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    location: str = ""
    job_url: str | None = None
    origin_url: str | None = None
    description: str = ""
    post_date: str | None = None
    search_keyword: str | None = None
    search_location: str | None = None
    search_region: str | None = None
    search_category: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    fit: FitScore | None = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def dedup_key(self) -> str:
        """Stable identity key for duplicate filtering."""
        if self.job_url:
            return f"opportunity:url:{_normalize_key_part(self.job_url)}"
        return f"opportunity:hash:{_hash_key(self.company, self.job_title, self.location)}"


class CandidateProfile(BaseModel):
    """Public-safe candidate profile used for matching and demos."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    location: str = ""
    education: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    target_geography: list[str] = Field(default_factory=list)
    target_org_types: list[str] = Field(default_factory=list)
    preferred_levels: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    master_resume: dict = Field(default_factory=dict)

    @field_validator(
        "education",
        "skills",
        "target_geography",
        "target_org_types",
        "preferred_levels",
        "excluded_keywords",
        mode="before",
    )
    @classmethod
    def coerce_string_list(cls, value):
        """Allow YAML authors to provide either a string or a list of strings."""
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class GeneratedDocument(BaseModel):
    """A generated or planned document artifact."""

    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    path: str | None = None
    content: str | None = None
    format: str = "text"


class ApplicationPacket(BaseModel):
    """The output bundle for one opportunity."""

    model_config = ConfigDict(extra="forbid")

    opportunity: Opportunity
    candidate_name: str
    documents: list[GeneratedDocument] = Field(default_factory=list)
    audit_notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def packet_id(self) -> str:
        """Stable packet identity for idempotent generation."""
        return f"packet:{_hash_key(self.candidate_name, self.opportunity.dedup_key)}"
