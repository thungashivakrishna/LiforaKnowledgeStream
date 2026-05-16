"""Acquisition schemas — request/response contracts for content fetching."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ks.domain.enums import RunStatus


class FetchRequest(BaseModel):
    document_id: uuid.UUID
    force_refresh: bool = False


class FetchRunResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    status: RunStatus
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    
    model_config = {"from_attributes": True}


class FactTriple(BaseModel):
    subject: str = Field(description="The primary subject of the fact.")
    predicate: str = Field(description="The action or relationship.")
    object: str = Field(description="The object or value of the fact.")
    fact_text: str = Field(description="A full sentence describing the fact.")

    model_config = {"extra": "forbid"}


class IntelligenceAuditOutput(BaseModel):
    is_high_value: bool = Field(description="True if the document contains substantial clinical or nutritional details.")
    reason: str = Field(description="Reason for the decision.")
    suggested_links: list[str] = Field(default_factory=list, description="Links to follow if this page is just an index.")
    initial_facts: list[FactTriple] = Field(default_factory=list, description="Top 3 key facts extracted immediately if high value.")

    model_config = {"extra": "forbid"}

class DocumentVersionResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    version_hash: str
    fetched_at: datetime
    raw_object_key: str | None
    
    model_config = {"from_attributes": True}
