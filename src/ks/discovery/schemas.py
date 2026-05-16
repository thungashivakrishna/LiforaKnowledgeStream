"""Discovery schemas — request/response contracts for content discovery."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ks.domain.enums import DiscoveryDecision, DiscoveryMode, RunStatus


# ── Filter Profile ────────────────────────────────────────────────────────────

class DiscoveryFilterProfileRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    mode: DiscoveryMode = DiscoveryMode.GENERIC
    topics: list[str] = Field(default_factory=list)
    synonyms: dict[str, list[str]] = Field(default_factory=dict)
    frameworks: list[str] = Field(default_factory=list)
    max_candidates: int = Field(default=100, ge=1, le=1000)
    per_source_limit: int = Field(default=20, ge=1, le=100)
    reference_context: str | None = None


class DiscoveryFilterProfileResponse(BaseModel):
    id: uuid.UUID
    name: str
    mode: DiscoveryMode
    topics: list[str]
    max_candidates: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Discovery Run ─────────────────────────────────────────────────────────────

class DiscoveryRunRequest(BaseModel):
    mode: DiscoveryMode
    filter_profile_id: uuid.UUID | None = None
    source_ids: list[uuid.UUID] = Field(default_factory=list, description="Optional scope: specific sources only")
    framework_scope: list[str] = Field(default_factory=list)


class DiscoveryRunResponse(BaseModel):
    id: uuid.UUID
    mode: DiscoveryMode
    status: RunStatus
    started_at: datetime | None
    completed_at: datetime | None
    candidate_count: int
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedDiscoveryRunResponse(BaseModel):
    items: list[DiscoveryRunResponse]
    total: int
    limit: int
    offset: int


# ── Candidate Document ────────────────────────────────────────────────────────

class CandidateDocumentResponse(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    document_id: uuid.UUID
    canonical_url: str
    title: str | None
    score: float | None
    decision: DiscoveryDecision
    matched_terms: list[str]
    evaluated_at: datetime
    document_status: str | None = None

    model_config = {"from_attributes": True}


class PaginatedCandidateResponse(BaseModel):
    items: list[CandidateDocumentResponse]
    total: int
    limit: int
    offset: int


class DiscoveryRunDetailResponse(DiscoveryRunResponse):
    source_scope: dict | None = None
    framework_scope: dict | None = None
    candidates: list[CandidateDocumentResponse] = Field(default_factory=list)


# ── Intelligent Prioritization ────────────────────────────────────────────────

class DocumentRelevanceScoreOutput(BaseModel):
    clinical_relevance: float = Field(..., description="0.0 to 1.0 score for clinical/medical relevance")
    intent_match: float = Field(..., description="0.0 to 1.0 score matching the target topics/frameworks")
    evidence_likelihood: float = Field(..., description="0.0 to 1.0 likelihood of containing structured evidence (trials, protocols)")
    actionability: float = Field(..., description="0.0 to 1.0 score for practical clinical actionability")
    safety_value: float = Field(..., description="0.0 to 1.0 score for safety guidelines or contraindications presence")
    freshness: float = Field(..., description="0.0 to 1.0 score based on recency or evergreen status")
    commercial_bias_risk: float = Field(..., description="0.0 to 1.0 risk score of SEO spam or heavy commercial bias")
    source_trust_multiplier: float = Field(..., description="0.5 to 1.5 multiplier based on domain authority")
    
    overall_priority_score: float = Field(..., description="Final calculated score (0 to 100)")
    explanation: str = Field(..., description="Brief 1-sentence explanation of the score")
    recommended_action: str = Field(..., description="EXTRACT, QUEUE, METADATA_ONLY, or REJECT")
