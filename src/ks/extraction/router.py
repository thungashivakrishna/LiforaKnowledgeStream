"""Extraction router — API endpoints for document extraction."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from ks.extraction.schemas import ExtractionRequest, ExtractionRunResponse
from ks.extraction.service import ExtractionService

router = APIRouter(prefix="/extraction", tags=["Extraction"])


@router.post("/extract", response_model=ExtractionRunResponse)
async def start_extraction(
    data: ExtractionRequest, 
    db: AsyncSession = Depends(get_db_session)
):
    """Start an extraction run for a specific document."""
    service = ExtractionService(db)
    try:
        run = await service.start_extraction(data)
        await db.commit()
        return run
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/runs", response_model=dict)
async def list_extraction_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session)
):
    """List extraction runs with pagination."""
    service = ExtractionService(db)
    items, total = await service.list_extraction_runs(limit, offset)
    
    # Format for response
    formatted_items = [
        {
            "id": r.id,
            "document_id": r.document_id,
            "status": r.status,
            "extraction_quality": r.extraction_quality,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "error_message": r.error_message,
        } for r in items
    ]
    
    return {"items": formatted_items, "total": total, "limit": limit, "offset": offset}


@router.get("/runs/{run_id}", response_model=ExtractionRunResponse)
async def get_extraction_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)):
    """Get details of a specific extraction run."""
    service = ExtractionService(db)
    try:
        run = await service.get_extraction_run(run_id)
        return run
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
