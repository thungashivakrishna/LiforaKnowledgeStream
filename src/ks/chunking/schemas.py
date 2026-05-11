"""Chunking schemas — request/response contracts for chunking and embedding."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from ks.domain.enums import RunStatus


class ChunkingRequest(BaseModel):
    document_id: uuid.UUID
    force_refresh: bool = False
    embedding_model: str = "text-embedding-3-small" # Default litellm model


class ChunkRunResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    status: RunStatus
    chunk_count: int
    embedding_model: str | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    
    model_config = {"from_attributes": True}
