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
