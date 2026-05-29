import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from ks.library.schemas import LibraryDocumentListResponse, LibraryDocumentDetailResponse, LibraryDocumentListContainer
from ks.library.service import LibraryService

router = APIRouter(prefix="/library", tags=["Knowledge Library"])

@router.get("/documents", response_model=LibraryDocumentListContainer)
async def list_library_documents(
    q: str | None = Query(None, description="Search query for relevance-based results"),
    status: str | None = Query(None, description="Filter by document status"),
    framework: str | None = Query(None, description="Filter by framework"),
    source_type: str | None = Query(None, description="Filter by source type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session)
):
    """List all completed documents available in the Knowledge Library."""
    service = LibraryService(db)
    items, total = await service.list_documents(q, status, framework, source_type, limit, offset)
    
    formatted_items = []
    for doc in items:
        summary_preview = None
        if doc.summary and doc.summary.summary_text:
            # Provide a short preview of the summary
            summary_preview = doc.summary.summary_text[:150] + "..." if len(doc.summary.summary_text) > 150 else doc.summary.summary_text
            
        # Use model_validate to convert SQLAlchemy model to Pydantic
        # We manually add extra fields since they are not on the root model
        pydantic_doc = LibraryDocumentListResponse.model_validate(doc)
        pydantic_doc.summary_preview = summary_preview
        if doc.source:
            pydantic_doc.source_name = doc.source.name
            pydantic_doc.source_type = doc.source.source_type
        
        formatted_items.append(pydantic_doc)
        
    return LibraryDocumentListContainer(items=formatted_items, total=total, limit=limit, offset=offset)

@router.get("/documents/{document_id}", response_model=LibraryDocumentDetailResponse)
async def get_library_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)):
    """Get the full knowledge graph details (facts, tags, summary) for a specific document."""
    service = LibraryService(db)
    try:
        doc = await service.get_document_details(document_id)
        # Convert to pydantic and manually add source fields
        pydantic_doc = LibraryDocumentDetailResponse.model_validate(doc)
        if doc.source:
            pydantic_doc.source_name = doc.source.name
            pydantic_doc.source_type = doc.source.source_type
        return pydantic_doc
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/guidelines")
async def list_actionable_guidelines(db: AsyncSession = Depends(get_db_session)):
    """Fetch all actionable facts across all documents to form a personal health roadmap."""
    service = LibraryService(db)
    items = await service.get_actionable_guidelines()
    
    formatted_items = []
    for fact in items:
        formatted_items.append({
            "id": fact.id,
            "fact_text": fact.fact_text,
            "subject": fact.subject,
            "predicate": fact.predicate,
            "object": fact.object_,
            "confidence": fact.confidence,
            "document_title": fact.document.title if fact.document else None,
            "document_id": fact.document_id
        })
        
    return formatted_items

from pydantic import BaseModel
from typing import List, Optional

class UserProfileRequest(BaseModel):
    conditions: Optional[List[str]] = []
    goals: Optional[List[str]] = []
    allergies: Optional[List[str]] = []

@router.post("/personalized-protocol")
async def get_personalized_protocol(
    profile: UserProfileRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """Map a user's biological profile to the knowledge graph to extract highly personalized protocols."""
    service = LibraryService(db)
    items = await service.get_personalized_guidelines(profile.model_dump())
    
    formatted_items = {}
    for fact in items:
        # Check against allergies/contradictions
        conflict = False
        if profile.allergies:
            for allergy in profile.allergies:
                if allergy.lower() in fact.subject.lower() or allergy.lower() in fact.object_.lower():
                    conflict = True
                    break
        
        if not conflict:
            # Semantic Key for Deduplication
            key = f"{fact.subject.lower()}|{fact.object_.lower()}"
            
            # Extract tags for context
            tags = []
            if fact.document and fact.document.tags:
                tags = [{"type": t.tag_type, "value": t.tag_value} for t in fact.document.tags]
            
            framework = next((t["value"] for t in tags if t["type"] == "FRAMEWORK"), "General Health")
            topic = next((t["value"] for t in tags if t["type"] == "TOPIC"), None)

            item = {
                "id": str(fact.id),
                "fact_text": fact.fact_text,
                "subject": fact.subject,
                "predicate": fact.predicate,
                "object": fact.object_,
                "confidence": fact.confidence,
                "document_title": fact.document.title if fact.document else None,
                "document_id": str(fact.document_id) if fact.document_id else None,
                "framework": framework,
                "topic": topic
            }
            
            # Keep highest confidence for the same core insight
            if key not in formatted_items or fact.confidence > formatted_items[key]["confidence"]:
                formatted_items[key] = item
    
    return sorted(formatted_items.values(), key=lambda x: x["confidence"], reverse=True)

class EditFactRequest(BaseModel):
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    fact_text: Optional[str] = None

@router.put("/facts/{fact_id}")
async def edit_fact(
    fact_id: uuid.UUID,
    data: EditFactRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """Edit an extracted fact during the clinical audit phase."""
    from ks.domain.models import KnowledgeFact
    from sqlalchemy import select
    
    res = await db.execute(select(KnowledgeFact).where(KnowledgeFact.id == fact_id))
    fact = res.scalar_one_or_none()
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")
        
    if data.subject is not None:
        fact.subject = data.subject
    if data.predicate is not None:
        fact.predicate = data.predicate
    if data.object is not None:
        fact.object_ = data.object
    if data.fact_text is not None:
        fact.fact_text = data.fact_text
        
    await db.commit()
    return {"message": "Fact updated successfully"}

@router.delete("/facts/{fact_id}")
async def delete_fact(
    fact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session)
):
    """Delete a low-confidence fact during the clinical audit phase."""
    from ks.domain.models import KnowledgeFact
    from sqlalchemy import select
    
    res = await db.execute(select(KnowledgeFact).where(KnowledgeFact.id == fact_id))
    fact = res.scalar_one_or_none()
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")
        
    await db.delete(fact)
    await db.commit()
    return {"message": "Fact deleted successfully"}

@router.get("/intelligence")
async def get_library_intelligence(db: AsyncSession = Depends(get_db_session)):
    """Fetch high-level intelligence metrics for the entire knowledge base."""
    service = LibraryService(db)
    stats = await service.get_library_intelligence()
    
    # Format recent findings
    findings = []
    for f in stats["recent_findings"]:
        findings.append({
            "id": f.id,
            "fact_text": f.fact_text,
            "subject": f.subject,
            "predicate": f.predicate,
            "object": f.object_,
            "confidence": f.confidence,
            "document_title": f.document.title if f.document else None
        })
    
    stats["recent_findings"] = findings
    return stats

@router.get("/clinical-quality/metrics")
async def get_clinical_quality_metrics(db: AsyncSession = Depends(get_db_session)):
    """Fetch structured levels of evidence (LoE) and domain audit logs for the clinical hub."""
    service = LibraryService(db)
    stats = await service.get_clinical_quality_metrics()
    
    # Format critic audits
    audits = []
    for f in stats["critic_audits"]:
        audits.append({
            "id": str(f.id),
            "fact_text": f.fact_text,
            "subject": f.subject,
            "predicate": f.predicate,
            "object": f.object_,
            "confidence": f.confidence,
            "critique": f.critique,
            "document_title": f.document.title if f.document else "Unknown Document",
            "document_id": str(f.document.id) if f.document else None
        })
    stats["critic_audits"] = audits
    return stats

@router.get("/clinical-quality/pathways")
async def get_clinical_quality_pathways(db: AsyncSession = Depends(get_db_session)):
    """Fetch structured subject-predicate-object pathways mapping interventions to biomarkers/symptoms."""
    service = LibraryService(db)
    return await service.get_clinical_quality_pathways()


