"""Source registry Pydantic schemas — request/response contracts."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from ks.domain.enums import (
    Framework, ReviewDecision, SourceApprovalStatus, SourceType,
)


# ── Shared ────────────────────────────────────────────────────────────────────

class CrawlPolicy(BaseModel):
    depth: int = Field(default=2, ge=1, le=5)
    allow_patterns: list[str] = Field(default_factory=list)
    block_patterns: list[str] = Field(default_factory=list)
    robots_respect: bool = True


class ExtractionProfile(BaseModel):
    preferred_extractor: str = "auto"
    table_extraction: bool = False
    custom_selectors: dict[str, str] = Field(default_factory=dict)


# ── Source Requests ───────────────────────────────────────────────────────────

class SourceCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    root_url: str = Field(..., description="Canonical root URL of the source")
    source_type: SourceType
    primary_framework: Framework
    secondary_frameworks: list[Framework] = Field(default_factory=list)
    language: str = Field(default="en", max_length=10)
    region: str | None = Field(default=None, max_length=100)
    trust_tier: int = Field(default=3, ge=1, le=5)
    crawl_policy: CrawlPolicy = Field(default_factory=CrawlPolicy)
    extraction_profile: ExtractionProfile = Field(default_factory=ExtractionProfile)
    freshness_days: int = Field(default=30, ge=1, le=365)
    review_notes: str | None = None


class SourceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    source_type: SourceType | None = None
    primary_framework: Framework | None = None
    secondary_frameworks: list[Framework] | None = None
    language: str | None = None
    region: str | None = None
    trust_tier: int | None = Field(default=None, ge=1, le=5)
    crawl_policy: CrawlPolicy | None = None
    extraction_profile: ExtractionProfile | None = None
    freshness_days: int | None = Field(default=None, ge=1, le=365)
    review_notes: str | None = None


class SourceActionRequest(BaseModel):
    actor: str = Field(default="admin", max_length=255)
    reason: str | None = None
    notes: str | None = None


class SourceReviewRequest(BaseModel):
    actor: str = Field(default="admin", max_length=255)
    decision: ReviewDecision
    reason: str | None = None
    notes: str | None = None


class SourceListFilters(BaseModel):
    approval_status: SourceApprovalStatus | None = None
    framework: Framework | None = None
    trust_tier: int | None = Field(default=None, ge=1, le=5)
    source_type: SourceType | None = None
    search: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


# ── Policy Schemas ────────────────────────────────────────────────────────────

class PolicyScoreRequest(BaseModel):
    authority: float = Field(..., ge=0.0, le=1.0)
    evidence_orientation: float = Field(..., ge=0.0, le=1.0)
    transparency: float = Field(..., ge=0.0, le=1.0)
    stability: float = Field(..., ge=0.0, le=1.0)
    relevance: float = Field(..., ge=0.0, le=1.0)
    extraction_feasibility: float = Field(..., ge=0.0, le=1.0)
    safety_risk: float = Field(..., ge=0.0, le=1.0)
    policy_compliance: float = Field(..., ge=0.0, le=1.0)


class PolicyScoreResponse(BaseModel):
    composite_score: float
    recommended_tier: int
    dimensions: dict[str, float]


# ── Source Responses ──────────────────────────────────────────────────────────

class FrameworkMapResponse(BaseModel):
    framework: Framework
    is_primary: bool

    model_config = {"from_attributes": True}


class SourceResponse(BaseModel):
    id: uuid.UUID
    name: str
    root_url: str
    source_type: SourceType
    language: str
    region: str | None
    trust_tier: int
    approval_status: SourceApprovalStatus
    freshness_days: int
    created_at: datetime
    updated_at: datetime
    framework_maps: list[FrameworkMapResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class SourceDetailResponse(SourceResponse):
    authority_score: float | None
    evidence_score: float | None
    transparency_score: float | None
    stability_score: float | None
    crawl_policy: dict[str, Any] | None
    extraction_profile: dict[str, Any] | None
    review_notes: str | None


class SourceReviewResponse(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    action: str
    actor: str
    decision: ReviewDecision | None
    reason: str | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceListResponse(BaseModel):
    items: list[SourceResponse]
    total: int
    limit: int
    offset: int
