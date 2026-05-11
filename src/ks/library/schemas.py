import uuid
from datetime import date, datetime
from pydantic import BaseModel

class LibraryFactResponse(BaseModel):
    id: uuid.UUID
    fact_text: str
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    confidence: float | None = None

    class Config:
        from_attributes = True

class LibraryTagResponse(BaseModel):
    id: uuid.UUID
    tag_type: str
    tag_value: str

    class Config:
        from_attributes = True

class LibrarySummaryResponse(BaseModel):
    id: uuid.UUID
    summary_text: str
    generated_by: str | None = None

    class Config:
        from_attributes = True

class LibraryDocumentListResponse(BaseModel):
    id: uuid.UUID
    title: str | None = None
    canonical_url: str
    status: str
    publication_date: date | None = None
    author: str | None = None
    source_name: str | None = None
    source_type: str | None = None
    created_at: datetime
    
    # We can include a short summary and tags in the list view
    summary_preview: str | None = None
    relevance_score: float | None = None
    tags: list[LibraryTagResponse] = []

    class Config:
        from_attributes = True

class LibraryDocumentDetailResponse(LibraryDocumentListResponse):
    summary: LibrarySummaryResponse | None = None
    facts: list[LibraryFactResponse] = []
    
    class Config:
        from_attributes = True

class LibraryDocumentListContainer(BaseModel):
    items: list[LibraryDocumentListResponse]
    total: int
    limit: int
    offset: int
