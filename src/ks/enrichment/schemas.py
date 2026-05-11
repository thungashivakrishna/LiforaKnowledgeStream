"""Enrichment schemas — request/response contracts for knowledge enrichment."""
import uuid
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field

from ks.domain.enums import RunStatus, Framework


class EnrichmentRequest(BaseModel):
    document_id: uuid.UUID
    force_refresh: bool = False
    model: str = "deepseek/deepseek-chat" # Primary model


class EnrichmentRunResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    status: RunStatus
    model_used: str | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    
    model_config = {"from_attributes": True}


# --- LLM Structured Output Schemas ---

class FactOutput(BaseModel):
    fact_text: str = Field(description="A clear, standalone statement of fact extracted from the text.")
    subject: str = Field(description="The primary entity or subject the fact is about.")
    predicate: str = Field(description="The relationship or action connecting subject and object.")
    object_value: str = Field(description="The target entity, value, or object of the fact.")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0 of how well supported this fact is by the text.")
    source_span: str = Field(description="A short quote from the source text that supports this fact.")


class LLMEnrichmentOutput(BaseModel):
    summary: str = Field(description="A concise summary of the document, 2-3 sentences max.")
    primary_framework: Framework = Field(description="The single most relevant health framework for this document.")
    secondary_frameworks: List[Framework] = Field(description="Other relevant frameworks, if any. Can be empty.")
    topics: List[str] = Field(description="A list of 3-7 key topics or keywords covered in the text.")
    conditions: List[str] = Field(default_factory=list, description="Medical conditions or diseases mentioned.")
    symptoms: List[str] = Field(default_factory=list, description="Associated symptoms mentioned.")
    interventions: List[str] = Field(default_factory=list, description="Medications, procedures, or lifestyle interventions.")
    nutrients: List[str] = Field(default_factory=list, description="Specific nutrients, minerals, or vitamins.")
    populations: List[str] = Field(default_factory=list, description="Target populations (e.g., 'Adults', 'Pregnant women').")
    facts: List[FactOutput] = Field(description="A list of 2-5 core domain facts extracted from the text.")
