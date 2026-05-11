"""Graph schemas — request/response contracts for knowledge graph synchronization."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from ks.domain.enums import RunStatus


class GraphSyncRequest(BaseModel):
    document_id: uuid.UUID
    force_refresh: bool = False


class GraphRunResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    status: RunStatus
    nodes_created: int
    edges_created: int
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    
    model_config = {"from_attributes": True}
