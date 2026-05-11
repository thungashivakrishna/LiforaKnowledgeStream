"""Chunking router — API endpoints for chunking and embedding documents."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from ks.chunking.schemas import ChunkingRequest, ChunkRunResponse
from ks.chunking.service import ChunkingService

router = APIRouter(prefix="/chunking", tags=["Chunking"])


@router.post("/chunk", response_model=ChunkRunResponse)
async def start_chunking(
    data: ChunkingRequest, 
    db: AsyncSession = Depends(get_db_session)
):
    """Start a chunking and embedding run for a specific document."""
    service = ChunkingService(db)
    try:
        run = await service.start_chunking(data)
        await db.commit()
        return run
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/runs", response_model=dict)
async def list_chunk_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session)
):
    """List chunking runs with pagination."""
    service = ChunkingService(db)
    items, total = await service.list_chunk_runs(limit, offset)
    
    # Format for response
    formatted_items = [
        {
            "id": r.id,
            "document_id": r.document_id,
            "status": r.status,
            "chunk_count": r.chunk_count,
            "embedding_model": r.embedding_model,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "error_message": r.error_message,
        } for r in items
    ]
    
    return {"items": formatted_items, "total": total, "limit": limit, "offset": offset}


@router.get("/runs/{run_id}", response_model=ChunkRunResponse)
async def get_chunk_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)):
    """Get details of a specific chunking run."""
    service = ChunkingService(db)
    try:
        run = await service.get_chunk_run(run_id)
        return run
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
