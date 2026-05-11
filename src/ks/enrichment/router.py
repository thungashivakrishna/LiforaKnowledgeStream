"""Enrichment router — API endpoints for document knowledge enrichment."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from ks.enrichment.schemas import EnrichmentRequest, EnrichmentRunResponse
from ks.enrichment.service import EnrichmentService

router = APIRouter(prefix="/enrichment", tags=["Enrichment"])


@router.post("/enrich", response_model=EnrichmentRunResponse)
async def start_enrichment(
    data: EnrichmentRequest, 
    db: AsyncSession = Depends(get_db_session)
):
    """Start an enrichment run for a specific document."""
    service = EnrichmentService(db)
    try:
        run = await service.start_enrichment(data)
        await db.commit()
        return run
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/runs", response_model=dict)
async def list_enrichment_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session)
):
    """List enrichment runs with pagination."""
    service = EnrichmentService(db)
    items, total = await service.list_enrichment_runs(limit, offset)
    
    # Format for response
    formatted_items = [
        {
            "id": r.id,
            "document_id": r.document_id,
            "status": r.status,
            "model_used": r.model_used,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "error_message": r.error_message,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "total_tokens": r.total_tokens,
        } for r in items
    ]
    
    return {"items": formatted_items, "total": total, "limit": limit, "offset": offset}


@router.get("/runs/{run_id}", response_model=EnrichmentRunResponse)
async def get_enrichment_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)):
    """Get details of a specific enrichment run."""
    service = EnrichmentService(db)
    try:
        run = await service.get_enrichment_run(run_id)
        return run
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
