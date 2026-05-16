"""Extraction schemas — request/response contracts for content extraction."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from ks.domain.enums import RunStatus, ExtractionQuality


class ExtractionRequest(BaseModel):
    document_id: uuid.UUID
    force_refresh: bool = False
    use_ocr: bool = True
    use_llm: bool = False


class ExtractionRunResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    status: RunStatus
    extraction_quality: ExtractionQuality | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    

class VerificationResult(BaseModel):
    is_hallucination: bool
    confidence_score: float
    critique: str
    suggested_fix: str | None = None
